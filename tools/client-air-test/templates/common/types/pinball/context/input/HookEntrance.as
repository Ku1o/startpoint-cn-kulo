package pinball.context.input
{
   public interface HookEntrance
   {

      function readyWithHandler(param1:Object, param2:Function, param3:Object = undefined) : void;

      function ready(param1:Object, param2:Object = undefined) : void;

      function instantWithHandler(param1:Object, param2:Function, param3:Object = undefined) : void;

      function instant(param1:Object, param2:Object = undefined) : void;
   }
}
