import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.abc.ABC;
import com.jpexs.decompiler.flash.abc.types.MethodBody;
import com.jpexs.decompiler.flash.tags.ABCContainerTag;
import java.io.*;
import java.util.*;

/** Independent FFDec check for an equal-count, explicitly named body patch. */
public final class CompareExactBodies {
    static SWF load(String name) throws Exception {
        try (InputStream in = new BufferedInputStream(new FileInputStream(name))) { return new SWF(in, true); }
    }
    public static void main(String[] args) throws Exception {
        SWF left=load(args[0]), right=load(args[1]);
        List<ABCContainerTag> la=left.getAbcList(), ra=right.getAbcList();
        if(la.size()!=ra.size()) throw new IllegalStateException("ABC count changed");
        List<String> changed=new ArrayList<>(); int count=0;
        for(int n=0;n<la.size();n++) {
            ABC a=la.get(n).getABC(), b=ra.get(n).getABC();
            if(a.bodies.size()!=b.bodies.size()) throw new IllegalStateException("Body count changed");
            count+=a.bodies.size();
            for(int i=0;i<a.bodies.size();i++) {
                MethodBody x=a.bodies.get(i), y=b.bodies.get(i);
                if(x.method_info!=y.method_info || x.max_stack!=y.max_stack || x.max_regs!=y.max_regs
                    || x.init_scope_depth!=y.init_scope_depth || x.max_scope_depth!=y.max_scope_depth
                    || !Arrays.equals(x.getCodeBytes(),y.getCodeBytes())) changed.add(n+":"+i);
            }
        }
        if(!String.join(",",changed).equals(args[2])) throw new IllegalStateException("Unexpected changes: "+changed);
        if(count!=96404) throw new IllegalStateException("Unexpected cumulative body count: "+count);
        System.out.println("PASS bodies="+count+" changed="+changed);
    }
}
