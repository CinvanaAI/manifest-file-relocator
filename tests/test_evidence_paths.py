import json
from pathlib import Path
import pytest
from manifest_file_relocator import build_plan,execute_plan,rollback


def make_plan(tmp_path):
    import shutil
    root=tmp_path/'workspace';shutil.copytree(Path(__file__).resolve().parents[1]/'examples/workspace',root)
    return root,build_plan(root,Path(__file__).resolve().parents[1]/'examples/manifest.json')


@pytest.mark.parametrize('side',['source','destination'])
def test_execute_evidence_cannot_alias_data_even_with_force(tmp_path,side):
    root,plan=make_plan(tmp_path);item=plan['items'][0];source=root/item['source'];original=source.read_bytes()
    with pytest.raises(ValueError,match='overlaps'):
        execute_plan(root,plan,plan['plan_sha256'],journal_path=root/item[side],replace_journal=True)
    assert source.read_bytes()==original
    assert not (root/item['destination']).exists()


@pytest.mark.parametrize('side',['source','destination'])
def test_rollback_evidence_cannot_alias_data_even_with_force(tmp_path,side):
    root,plan=make_plan(tmp_path);journal=execute_plan(root,plan,plan['plan_sha256']);item=plan['items'][0];moved=root/item['destination'];original=moved.read_bytes()
    with pytest.raises(ValueError,match='overlaps'):
        rollback(root,journal,journal['journal_sha256'],output_path=root/item[side],replace_output=True)
    assert moved.read_bytes()==original
    assert not (root/item['source']).exists()


def test_evidence_cannot_create_directory_at_destination(tmp_path):
    root,plan=make_plan(tmp_path);destination=root/plan['items'][0]['destination']
    with pytest.raises(ValueError,match='overlaps'):
        execute_plan(root,plan,plan['plan_sha256'],journal_path=destination/'journal.json')
    assert not destination.exists()


@pytest.mark.skipif(__import__('os').name != 'nt', reason='Windows case-insensitive Path semantics')
def test_case_aliased_destinations_rejected_by_planner_and_executor(tmp_path):
    from manifest_file_relocator.planner import canonical_hash,sha256_file
    root=tmp_path/'case';root.mkdir()
    for folder,name,text in [('first','item.txt','first'),('second','ITEM.txt','second')]:
        (root/folder).mkdir();(root/folder/name).write_text(text)
    manifest=root/'manifest.json';manifest.write_text(json.dumps({'version':1,'operations':[
        {'id':'one','from':'first','to':'sorted','file':'item.txt'},
        {'id':'two','from':'second','to':'sorted','file':'ITEM.txt'}]}))
    with pytest.raises(ValueError,match='aliased'):
        build_plan(root,manifest)
    items=[]
    for folder,name in [('first','item.txt'),('second','ITEM.txt')]:
        source=root/folder/name
        items.append({'source':folder+'/'+name,'destination':'sorted/'+name,'bytes':source.stat().st_size,'sha256':sha256_file(source)})
    plan={'version':1,'items':items,'item_count':2};plan['plan_sha256']=canonical_hash(plan,'plan_sha256')
    with pytest.raises(ValueError,match='aliased'):
        execute_plan(root,plan,plan['plan_sha256'])
    assert (root/'first/item.txt').read_text()=='first'
    assert (root/'second/ITEM.txt').read_text()=='second'
    assert not (root/'sorted').exists()


def test_repeated_source_is_rejected_even_in_resealed_plan(tmp_path):
    from manifest_file_relocator.planner import canonical_hash
    root,plan=make_plan(tmp_path)
    plan['items'][1]['source']=plan['items'][0]['source']
    plan['plan_sha256']=canonical_hash(plan,'plan_sha256')
    with pytest.raises(ValueError,match='duplicate'):
        execute_plan(root,plan,plan['plan_sha256'])
    assert all((root/item['source']).exists() for item in plan['items'])
