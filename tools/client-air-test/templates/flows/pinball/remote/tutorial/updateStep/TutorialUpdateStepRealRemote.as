package pinball.remote.tutorial.updateStep {
import haxe.ds.Option;
import pinball.context.remote.real.RealRemoteService;
import pinball.remote.common.ResponseData;
import pinball.remote.tutorial.updateStep.TutorialUpdateStepKind;
import pinball.remote.tutorial.updateStep.TutorialUpdateStepRemoteInput;
public dynamic class TutorialUpdateStepRealRemote extends RealRemoteService {
public var kind:TutorialUpdateStepKind;
public var dispatcher:Option;
public function TutorialUpdateStepRealRemote(){super();}
public function successHandler(p0:ResponseData):void{}
public function sendInput(p0:TutorialUpdateStepRemoteInput):void{}
}}