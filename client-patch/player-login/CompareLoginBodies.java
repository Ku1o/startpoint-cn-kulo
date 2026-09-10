import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.abc.ABC;
import com.jpexs.decompiler.flash.abc.types.MethodBody;
import com.jpexs.decompiler.flash.tags.ABCContainerTag;
import java.io.*;
import java.util.*;
/** Independent parser audit of the cumulative payload, including the one added ABC. */
public final class CompareLoginBodies {
  static SWF load(String path) throws Exception {
    try(InputStream in=new BufferedInputStream(new FileInputStream(path))){return new SWF(in,true);}
  }
  public static void main(String[] args) throws Exception {
    List<ABCContainerTag> a=load(args[0]).getAbcList(),b=load(args[1]).getAbcList();
    if(b.size()!=a.size()+1)throw new IllegalStateException("ABC inventory changed");
    int mainIndex=0;
    for(int n=1;n<a.size();n++)if(a.get(n).getABC().bodies.size()>a.get(mainIndex).getABC().bodies.size())mainIndex=n;
    if(mainIndex!=Integer.parseInt(args[4]))throw new IllegalStateException("main ABC index mismatch");
    List<String> changes=new ArrayList<>();int count=0;
    for(int n=0;n<a.size();n++){
      ABC x=a.get(n).getABC(),y=b.get(n+(n>=mainIndex?1:0)).getABC();
      if(x.bodies.size()!=y.bodies.size())throw new IllegalStateException("game method inventory changed");
      count+=x.bodies.size();
      for(int i=0;i<x.bodies.size();i++){
        MethodBody l=x.bodies.get(i),r=y.bodies.get(i);
        if(l.method_info!=r.method_info || l.max_regs!=r.max_regs || l.init_scope_depth!=r.init_scope_depth || l.max_scope_depth!=r.max_scope_depth)throw new IllegalStateException("ABI "+n+":"+i);
        if(l.max_stack!=r.max_stack || !Arrays.equals(l.getCodeBytes(),r.getCodeBytes()))changes.add(n+":"+i);
      }
    }
    if(count!=Integer.parseInt(args[5]) || !String.join(",",changes).equals(args[2]))throw new IllegalStateException("unexpected changes "+changes);
    ABC helper=b.get(mainIndex).getABC();
    if(helper.instance_info.size()!=1 || helper.bodies.size()!=Integer.parseInt(args[3]))throw new IllegalStateException("helper mismatch");
    System.out.println("PASS original_bodies="+count+" helper_bodies="+helper.bodies.size()+" changes="+changes);
  }
}
