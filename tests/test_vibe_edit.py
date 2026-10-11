from fastapi.testclient import TestClient

from vibe_trending import app as module
from vibe_trending.models import Plan
from vibe_trending.store import Store


def test_vibe_edit_preview_apply_preserves_manual_and_conflicts(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'store', Store(tmp_path / 'edit.sqlite'))
    original = Plan(title='GDP', series=[{'name':'中国GDP','indicator':'NY.GDP.MKTP.CD','country':'CHN','unit':'美元'}])
    candidate = original.model_copy(deep=True)
    candidate.series[0].name='中国GDP（改名）'
    candidate.series.append(candidate.series[0].model_copy(update={'country':'USA','name':'美国GDP'}))
    class Agent:
        async def plan(self, prompt):
            assert '当前策略' in prompt
            assert '新增美国' in prompt
            return candidate
    monkeypatch.setattr(module, 'agent', Agent())
    with TestClient(module.app) as client:
        p=client.post('/api/projects',json={'plan':original.model_dump()}).json()
        p['series']=[{**original.series[0].model_dump(),'id':module.series_identity(original.series[0]),'points':[{'date':'2024','value':99,'manual':True,'quality':'manual_confirmed','source_url':'https://example.com'}]}]
        module.store.save(p,'test_data')
        base='/api/projects/'+p['id']
        preview=client.post(base+'/vibe-edit',json={'prompt':'新增美国，原序列改名'}).json()
        assert len(preview['changes']['added'])==1
        assert module.store.get(p['id'])['plan']['title']=='GDP'
        request={'plan':preview['plan'],'base_revision':preview['base_revision'],'instruction':'新增美国，原序列改名'}
        response=client.put(base+'/plan',json=request)
        assert response.status_code==200
        updated=response.json()
        assert len(updated['plan']['series'])==2
        assert updated['series'][0]['points'][0]['manual']
        assert updated['series'][0]['points'][0]['value']==99
        assert updated['series'][0]['name']=='中国GDP（改名）'
        assert updated['audit'][0]['kind']=='plan_edit'
        assert client.put(base+'/plan',json=request).status_code==409
        # Replacing the source cannot relabel existing numbers as new evidence.
        new_plan=Plan.model_validate(updated['plan'])
        new_plan.series[0].source='web'
        new_plan.series[0].query='中国GDP官方数据'
        response=client.put(base+'/plan',json={'plan':new_plan.model_dump(),'base_revision':updated['updated_at'],'instruction':'改为网页来源'})
        assert response.status_code==200
        assert response.json()['series']==[]
        assert any(v['reason']=='plan_edit' for v in module.store.versions(p['id']))
        new_plan.series[0].source='unregistered'
        assert client.put(base+'/plan',json={'plan':new_plan.model_dump(),'base_revision':response.json()['updated_at'],'instruction':'测试非法来源'}).status_code==422
