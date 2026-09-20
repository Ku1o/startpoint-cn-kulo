import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.abc.ABC;
import com.jpexs.decompiler.flash.abc.types.MethodBody;
import com.jpexs.decompiler.flash.tags.ABCContainerTag;
import java.io.*;
import java.util.*;

public final class CompareBodies {
    static SWF load(String path)throws Exception{try(InputStream in=new BufferedInputStream(new FileInputStream(path))){return new SWF(in,true);}}
    public static void main(String[] args)throws Exception{
        List<ABCContainerTag> before=load(args[0]).getAbcList(),after=load(args[1]).getAbcList();
        if(before.size()!=292 || after.size()!=293)throw new IllegalStateException("ABC inventory");
        Set<Integer> expected=new TreeSet<Integer>(Arrays.asList(4336,4373,4374,5209,5259,5263,5264,5322,15140,20565,28920,28956,28963,28971,30852,38042,38045,38046,38073,38074,38076,38428,38430,38431,38432,50845,51007,51008,58883,60835,63233,63250,76162,76168,76169,82500,82509,92540));
        Set<Integer> changed=new TreeSet<Integer>();int count=0;
        for(int n=0;n<before.size();n++){
            ABC a=before.get(n).getABC(),b=after.get(n+(n==291?1:0)).getABC();count+=a.bodies.size();
            if(a.bodies.size()!=b.bodies.size() || a.instance_info.size()!=b.instance_info.size())throw new IllegalStateException("class/method inventory");
            for(int i=0;i<a.bodies.size();i++){
                MethodBody x=a.bodies.get(i),y=b.bodies.get(i);
                if(x.method_info!=y.method_info || x.max_regs!=y.max_regs || x.init_scope_depth!=y.init_scope_depth || x.max_scope_depth!=y.max_scope_depth || x.exceptions.length!=y.exceptions.length)throw new IllegalStateException("method ABI "+n+":"+i);
                if(x.max_stack!=y.max_stack || !Arrays.equals(x.getCodeBytes(),y.getCodeBytes())){
                    if(n!=291)throw new IllegalStateException("unexpected helper change");changed.add(i);
                }
            }
        }
        if(count!=96543 || !changed.equals(expected))throw new IllegalStateException("unexpected method set "+changed);
        ABC helper=after.get(291).getABC();
        if(helper.instance_info.size()!=1 || helper.bodies.size()!=20)throw new IllegalStateException("helper inventory");
        System.out.println("PASS original_bodies=96543 unchanged_bodies=96505 added_bodies=20 changed="+changed);
    }
}
