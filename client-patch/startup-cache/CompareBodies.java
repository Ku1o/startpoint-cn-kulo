import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.abc.ABC;
import com.jpexs.decompiler.flash.abc.types.MethodBody;
import com.jpexs.decompiler.flash.tags.ABCContainerTag;
import java.io.*;
import java.util.*;

/** Independent FFDec parser readback of all 96,515 original method bodies. */
public final class CompareBodies {
  static SWF load(String path) throws Exception {
    try(InputStream in=new BufferedInputStream(new FileInputStream(path))){return new SWF(in,true);}
  }
  public static void main(String[] args) throws Exception {
    List<ABCContainerTag> a=load(args[0]).getAbcList(),b=load(args[1]).getAbcList();
    if(a.size()!=288 || b.size()!=289)throw new IllegalStateException("ABC inventory");
    Set<String> expected=new HashSet<>(Arrays.asList("285:7","286:0","287:47796"));
    Set<String> changed=new HashSet<>();int count=0;
    for(int n=0;n<a.size();n++){
      ABC x=a.get(n).getABC(),y=b.get(n+(n==287?1:0)).getABC();
      if(x.bodies.size()!=y.bodies.size() || x.instance_info.size()!=y.instance_info.size())throw new IllegalStateException("class/method inventory");
      count+=x.bodies.size();
      for(int i=0;i<x.bodies.size();i++){
        MethodBody l=x.bodies.get(i),r=y.bodies.get(i);String key=n+":"+i;
        if(l.method_info!=r.method_info || l.init_scope_depth!=r.init_scope_depth)throw new IllegalStateException("ABI "+key);
        boolean different=l.max_regs!=r.max_regs || l.max_scope_depth!=r.max_scope_depth
          || l.max_stack!=r.max_stack || !Arrays.equals(l.getCodeBytes(),r.getCodeBytes());
        if(different)changed.add(key);
      }
    }
    if(count!=96515 || !changed.equals(expected))throw new IllegalStateException("unexpected changes "+changed);
    ABC helper=b.get(287).getABC();
    if(helper.instance_info.size()!=1 || helper.bodies.size()!=5)throw new IllegalStateException("helper inventory");
    System.out.println("PASS original_bodies="+count+" added_bodies=5 changed="+changed);
  }
}
