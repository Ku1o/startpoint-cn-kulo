import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.abc.ABC;
import com.jpexs.decompiler.flash.abc.types.MethodBody;
import com.jpexs.decompiler.flash.tags.ABCContainerTag;
import java.io.BufferedInputStream;
import java.io.FileInputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class CompareMethodBodies {
    private static SWF load(String path) throws Exception {
        try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(path))) {
            return new SWF(input, true);
        }
    }

    private static boolean same(MethodBody left, MethodBody right) {
        return left.method_info == right.method_info
            && left.max_stack == right.max_stack
            && left.max_regs == right.max_regs
            && left.init_scope_depth == right.init_scope_depth
            && left.max_scope_depth == right.max_scope_depth
            && Arrays.equals(left.getCodeBytes(), right.getCodeBytes());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("usage: CompareMethodBodies <baseline.swf> <candidate.swf>");
        }
        SWF baseline = load(args[0]);
        SWF candidate = load(args[1]);
        List<ABCContainerTag> baselineAbcs = baseline.getAbcList();
        List<ABCContainerTag> candidateAbcs = candidate.getAbcList();
        if (baselineAbcs.size() != candidateAbcs.size()) {
            throw new IllegalStateException("ABC tag count differs");
        }

        List<String> changed = new ArrayList<>();
        int total = 0;
        for (int abcIndex = 0; abcIndex < baselineAbcs.size(); abcIndex++) {
            ABC left = baselineAbcs.get(abcIndex).getABC();
            ABC right = candidateAbcs.get(abcIndex).getABC();
            if (left.bodies.size() != right.bodies.size()) {
                throw new IllegalStateException("method body count differs for ABC " + abcIndex);
            }
            total += left.bodies.size();
            for (int bodyIndex = 0; bodyIndex < left.bodies.size(); bodyIndex++) {
                if (!same(left.bodies.get(bodyIndex), right.bodies.get(bodyIndex))) {
                    changed.add(abcIndex + ":" + bodyIndex);
                }
            }
        }
        System.out.println("method_bodies=" + total);
        System.out.println("changed_count=" + changed.size());
        System.out.println("changed=" + String.join(",", changed));
    }
}
