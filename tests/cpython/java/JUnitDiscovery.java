import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import junit.framework.TestCase;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Find concrete JUnit 3/4 tests among the same source candidates as Ant. */
public final class JUnitDiscovery {
    public static void main(String[] names) throws Exception {
        for (String name : names) {
            Class<?> type = Class.forName(name, false, JUnitDiscovery.class.getClassLoader());
            boolean test = !Modifier.isAbstract(type.getModifiers()) && !type.isInterface();
            if (test) {
                test = TestCase.class.isAssignableFrom(type) || type.isAnnotationPresent(RunWith.class);
                for (Method method : type.getMethods()) {
                    test |= method.isAnnotationPresent(Test.class);
                    test |= method.getName().equals("suite")
                            && Modifier.isStatic(method.getModifiers())
                            && method.getParameterTypes().length == 0
                            && junit.framework.Test.class.isAssignableFrom(method.getReturnType());
                }
            }
            System.out.println((test ? "TEST " : "HELPER ") + name);
        }
    }
}
