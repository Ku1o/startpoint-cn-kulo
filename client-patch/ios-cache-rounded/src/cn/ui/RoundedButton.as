package cn.ui {
    import flash.utils.getDefinitionByName;
    public final class RoundedButton {
        public static function create(width:Number, height:Number, color:uint):Object {
            var CanvasClass:Class=getDefinitionByName("starling.display.Canvas") as Class;
            var PolygonClass:Class=getDefinitionByName("starling.geom.Polygon") as Class;
            var radius:Number=height/5;
            var vertices:Array=[];
            for(var corner:int=0;corner<4;corner++) {
                var cx:Number=corner==0 || corner==1 ? width-radius : radius;
                var cy:Number=corner==1 || corner==2 ? height-radius : radius;
                for(var step:int=0;step<=8;step++) {
                    var angle:Number=(-90+corner*90+step*90/8)*Math.PI/180;
                    vertices.push(cx+Math.cos(angle)*radius,cy+Math.sin(angle)*radius);
                }
            }
            var result:Object=new CanvasClass();
            result.beginFill(color);result.drawPolygon(new PolygonClass(vertices));result.endFill();
            return result;
        }
    }
}
