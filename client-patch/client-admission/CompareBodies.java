import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.abc.ABC;
import com.jpexs.decompiler.flash.abc.types.MethodBody;
import com.jpexs.decompiler.flash.tags.ABCContainerTag;
import java.io.*;
import java.util.*;

/** Independent FFDec parser: preserve every original method except the declared hooks. */
public final class CompareBodies {
  static SWF load(String path) throws Exception {
    try(InputStream in=new BufferedInputStream(new FileInputStream(path))){return new SWF(in,true);}
  }
  public static void main(String[] args) throws Exception {
    List<ABCContainerTag> a=load(args[0]).getAbcList(),b=load(args[1]).getAbcList();
    int prefix=Integer.parseInt(args[3]);
    if(b.size()!=a.size()+prefix)throw new IllegalStateException("ABC inventory changed");
    Set<String> expected=new TreeSet<>(Arrays.asList(args[2].split(","))), changes=new TreeSet<>();int count=0;
    for(int n=0;n<a.size();n++){
      ABC x=a.get(n).getABC(),y=b.get(n+prefix).getABC();
      if(x.bodies.size()!=y.bodies.size())throw new IllegalStateException("game method inventory changed");
      count+=x.bodies.size();
      for(int i=0;i<x.bodies.size();i++){
        String key=n+":"+i;MethodBody l=x.bodies.get(i),r=y.bodies.get(i);
        int extra=prefix>0 && key.equals("286:37")?2:0;
        if(l.method_info!=r.method_info || l.max_regs+extra!=r.max_regs || l.init_scope_depth!=r.init_scope_depth || l.max_scope_depth!=r.max_scope_depth)throw new IllegalStateException("ABI "+key);
        if(l.max_stack!=r.max_stack || !Arrays.equals(l.getCodeBytes(),r.getCodeBytes()))changes.add(key);
      }
    }
    if(count!=96543 || !changes.equals(expected))throw new IllegalStateException("unexpected changes "+changes);
    int classes=0,helperBodies=0;
    for(int i=0;i<prefix;i++){classes+=b.get(i).getABC().instance_info.size();helperBodies+=b.get(i).getABC().bodies.size();}
    if(classes!=prefix)throw new IllegalStateException("helper inventory changed");
    System.out.println("PASS original_bodies="+count+" helper_bodies="+helperBodies+" changes="+changes);
  }
}
