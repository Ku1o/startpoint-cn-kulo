import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.abc.ABC;
import com.jpexs.decompiler.flash.abc.types.MethodBody;
import com.jpexs.decompiler.flash.tags.ABCContainerTag;
import java.io.*;
import java.util.*;

/** Independent FFDec parser: exactly one helper ABC, and named insertion targets. */
public final class CompareDetailBodies {
    static SWF load(String path) throws Exception {
        try (InputStream in = new BufferedInputStream(new FileInputStream(path))) { return new SWF(in,true); }
    }
    public static void main(String[] args) throws Exception {
        List<ABCContainerTag> left=load(args[0]).getAbcList(),right=load(args[1]).getAbcList();
        if(right.size()!=left.size()+1) throw new IllegalStateException("ABC count drift");
        int helper=Integer.parseInt(args[3]);
        List<String> changed=new ArrayList<>(); int count=0;
        for(int n=0;n<left.size();n++) {
            ABC a=left.get(n).getABC(),b=right.get(n+(n>=helper?1:0)).getABC();
            if(a.bodies.size()!=b.bodies.size())throw new IllegalStateException("game method count drift");
            count+=a.bodies.size();
            for(int i=0;i<a.bodies.size();i++) {
                MethodBody x=a.bodies.get(i),y=b.bodies.get(i);
                if(x.method_info!=y.method_info || x.max_regs!=y.max_regs || x.init_scope_depth!=y.init_scope_depth
                    || x.max_scope_depth!=y.max_scope_depth)throw new IllegalStateException("game method ABI changed "+n+":"+i);
                if(x.max_stack!=y.max_stack || !Arrays.equals(x.getCodeBytes(),y.getCodeBytes()))changed.add(n+":"+i);
            }
        }
        if(!String.join(",",changed).equals(args[2]))throw new IllegalStateException("Unexpected changes "+changed);
        if(count!=96409)throw new IllegalStateException("Cumulative inventory drift "+count);
        ABC h=right.get(helper).getABC();
        if(h.instance_info.size()!=1 || h.bodies.size()!=Integer.parseInt(args[4]))throw new IllegalStateException("Unexpected helper definitions");
        System.out.println("PASS original_bodies="+count+" helper_bodies="+h.bodies.size()+" changed="+changed);
    }
}
