"""Read back the frozen SWF and bind independent preservation/runtime receipts."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'content-operations'))
import build_bridge as b
from build_town_theme import R10,RESPONSE,SELECT,sha
def verify(work,baseline):
 candidate=work/'candidate/town-theme-android.swf';digest=sha(candidate.read_bytes());assert sha(baseline.read_bytes())==R10
 old=b.sc.parts(baseline)[2];new=b.sc.parts(candidate)[2];assert len(new)==len(old)+1
 at,= [i for i,t in enumerate(new) if t[3] and t[2][4:].split(b'\0')[0]==b'town_theme_login']
 assert at>0 and new[at][3]
 changed=[];preserved_helpers=[];main_before=main_after=None
 for i,t in enumerate(old):
  result=new[i+(i>=at)]
  if bytes(t[1])==bytes(result[1]):
   if t[3]:
    for owner in ['cn.content::ContentOperationsState','cn.profile::PlayerHistoryState']:
     if any(t[3].mn_name(x[0])==owner for x in t[3].instances):preserved_helpers.append({'owner':owner,'bodies':len(t[3].bodies),'byteExact':True,'sha256':sha(t[3].serialize())})
   continue
  assert t[3] and result[3] and t[2]==result[2] and t[2][4:].split(b'\0')[0]==b'boot_ffc6'
  main_before=t[3];main_after=result[3];v=b.view(main_before);rv=b.view(main_after)
  assert len(main_before.bodies)==len(main_after.bodies)
  for j,body in enumerate(main_before.bodies):
   if b.p.freeze(body)!=b.p.freeze(main_after.bodies[j]):
    labels=[label for label,ids in v.by_label.items() if j in ids];changed+=labels
  for field in ['methods','instances','classes','scripts','metadata']:assert b.p.freeze(getattr(main_before,field))==b.p.freeze(getattr(main_after,field)),field
  for field in ['strings','ints','uints','doubles','namespaces','ns_sets','multinames']:assert b.p.freeze(getattr(main_before,field))==b.p.freeze(getattr(main_after,field)[:len(getattr(main_before,field))]),field
 assert set(changed)=={RESPONSE,SELECT},changed
 assert {(x['owner'],x['bodies']) for x in preserved_helpers}=={('cn.content::ContentOperationsState',85),('cn.profile::PlayerHistoryState',7)}
 profile_labels=['pinball.common.data.player_history::PlayerHistoryLogic/isWithinPeriod|1','pinball.scene.playerHistory.card::PlayerHistoryCardTopicLogic/getDateValues|1','pinball.scene.playerHistory.card::PlayerHistoryCardTopicView/getDateString|1','pinball.scene.playerProfile::PlayerProfileView/drawPlayerInfoForPlayerHistory|1','pinball.scene.playerHistory.card::PlayerHistoryCardLogic/createShareText|1','pinball.scene.playerHistory.card::PlayerHistoryCardTopicView/complete_mana_board_2|1','pinball.scene.playerHistory.card::PlayerHistoryCardTopicView/defeat_expert_single_boss|1']
 v=b.view(main_before);rv=b.view(main_after)
 for label in profile_labels:assert b.p.freeze(main_before.bodies[v.by_label[label][0]])==b.p.freeze(main_after.bodies[rv.by_label[label][0]])
 town_path=work/'native-final/air-town-result.json';profile_path=work/'profile-regression/air-native-result.json';negative_path=work/'native-negative-r10/air-town-result.json'
 town=json.loads(town_path.read_text(encoding='utf8'));profile=json.loads(profile_path.read_text(encoding='utf8'));negative=json.loads(negative_path.read_text(encoding='utf8'))
 assert town['passed'] and town['asyncTickExecuted'] and town['candidateSwfSha256']==digest and town['assertions']>=122
 assert profile['passed'] and profile['sourceSwfSha256']==digest and profile['productionInputsStable']
 assert negative['expectedMissingHooksDetected'] and negative['observedPassed'] is False and negative['candidateSwfSha256']==digest
 source_files=[HERE/'src/cn/town/TownThemeState.as',HERE/'build_town_theme.py',HERE/'native_runtime_fixtures.py',HERE/'verify_final.py',HERE/'README.md']
 receipts=[work/'candidate/cumulative-method-preservation.json',town_path,work/'native-final/production-method-import.json',profile_path,work/'profile-regression/production-native-import.json',negative_path]
 record={'schema':'town-theme-client-final/v1','candidateSwf':str(candidate),'candidateSwfSha256':digest,'inputSwf':str(baseline),'inputSwfSha256':R10,'addedDoAbcName':'town_theme_login','changedDoAbcName':'boot_ffc6','changedNativeMethods':changed,'changedNativeBodies':2,'nativeAbiPreserved':True,'constantPoolsAppendOnly':True,'nonTargetTagsByteExact':True,'nonTargetBodiesByteExact':True,'preservedHelpers':preserved_helpers,'preservedPriorProfileNativeMethods':profile_labels,'nativeRuntime':{'passed':True,'assertions':town['assertions'],'asyncTickExecuted':True,'receipt':str(town_path)},'matureProfileRegression':{'passed':True,'assertions':profile['assertions'],'receipt':str(profile_path)},'nativeR10MissingHooksNegative':{'expectedFailureDetected':True,'receipt':str(negative_path)},'sourceFiles':[{'path':str(p),'sha256':sha(p.read_bytes())} for p in source_files],'receipts':[{'path':str(p),'sha256':sha(p.read_bytes())} for p in receipts],'saveOrLocalBgmWrites':False,'apkPackaged':False,'registryChanged':False,'deviceTested':False,'serverOrDatabaseChanged':False,'limits':['fixture master and asset storage; no actual downloads/GPU/full game','native ResponseData constructor prologue only; remainder byte preserved','native annual period body uses bounded clock conversion fixture','APK package/signing and device acceptance are separate']}
 (work/'FINAL.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({'candidateSwfSha256':digest,'townAssertions':town['assertions'],'profileAssertions':profile['assertions'],'changedNativeBodies':2,'final':str(work/'FINAL.json')}))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);a=p.parse_args();verify(a.work,a.baseline)
if __name__=='__main__':main()
