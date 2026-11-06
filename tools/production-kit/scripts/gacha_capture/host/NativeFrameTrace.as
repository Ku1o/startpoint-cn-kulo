package {
  public final class NativeFrameTrace {
    public static function sample(scene:Object, tick:int):Object {
      var battle:Object=scene.myBattle;
      var squad:Object=battle.squadManager.primary;
      var ball:Object=squad.ball;
      var members:Array=[];
      for each(var memberOption:Object in squad.members){
        if(memberOption.index!==0){members.push(null);continue;}
        var member:Object=memberOption.params[0];
        members.push({hp:member.hp,skillRequests:member.actionSkillCount,
          skillExecutions:member.actionSkillExecutionCount,lastSkillInvokedFrame:optionInt(member.lastSkillInvokedFrame)});
      }
      var targets:Array=[];
      for each(var zone:Object in battle.zoneManager.zones){
        var enemies:Object=zone.enemyManager.enemies.iterator();
        while(enemies.hasNext())targets.push(target(enemies.next(),'enemy'));
        var zakos:Object=zone.zakoManager.activeZakos.iterator();
        while(zakos.hasNext())targets.push(target(zakos.next(),'zako'));
      }
      return {tick:tick,frame:battle.currentFrame,replayFrame:scene.state.currentFrame,
        previewState:scene.skillPreviewState.index,previewStateTag:scene.skillPreviewState.tag,
        inSkillCutin:battle.isPlayingSkillCutin(),
        ball:{x:ball.getPosX(),y:ball.getPosY(),vx:ball.get_vx(),vy:ball.get_vy(),state:ball.getState().index,stateTag:ball.getState().tag,stateFrame:ball.stateFrame},
        members:members,targets:targets};
    }
    private static function target(enemy:Object,kind:String):Object {
      return {kind:kind,id:enemy.enemyId,x:enemy.x,y:enemy.y,
        hp:enemy.getRealCurrentHealthPoint(),totalDamages:enemy.totalDamages};
    }
    private static function optionInt(value:Object):Object {
      return value.index===0 ? value.params[0] : null;
    }
  }
}
