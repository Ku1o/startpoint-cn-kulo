import com.jpexs.decompiler.flash.SWF;
import com.jpexs.decompiler.flash.abc.ABC;
import com.jpexs.decompiler.flash.tags.ABCContainerTag;
import java.io.BufferedInputStream;
import java.io.FileInputStream;

public final class FindMethodBody {
    public static void main(String[] args) throws Exception {
        if (args.length < 3 || (args.length - 1) % 2 != 0) {
            throw new IllegalArgumentException(
                "usage: FindMethodBody <swf> <class> <method> [<class> <method> ...]"
            );
        }
        try (BufferedInputStream input = new BufferedInputStream(new FileInputStream(args[0]))) {
            SWF swf = new SWF(input, true);
            for (int i = 1; i < args.length; i += 2) {
                String className = args[i];
                String methodName = args[i + 1];
                boolean found = false;
                int abcIndex = 0;
                for (ABCContainerTag container : swf.getAbcList()) {
                    ABC abc = container.getABC();
                    int bodyIndex = abc.findMethodBodyByName(className, methodName);
                    if (bodyIndex >= 0) {
                        System.out.println(
                            className + "." + methodName
                            + "\tabc=" + abcIndex
                            + "\tbody=" + bodyIndex
                        );
                        found = true;
                    }
                    abcIndex++;
                }
                if (!found) {
                    throw new IllegalStateException("method not found: " + className + "." + methodName);
                }
            }
        }
    }
}
