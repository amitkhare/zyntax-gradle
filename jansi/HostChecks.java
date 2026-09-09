import java.io.InputStream;
import java.util.Properties;
import org.fusesource.hawtjni.runtime.Library;
import org.fusesource.jansi.Ansi;

/** Host-only checks: do not load an Android ELF or alter reported OS/architecture. */
public final class HostChecks {
    public static void main(String[] args) throws Exception {
        require("1.18-zyntax.1".equals(Ansi.class.getPackage().getImplementationVersion()), "manifest identity");
        Properties properties = new Properties();
        try (InputStream input = Ansi.class.getResourceAsStream("jansi.properties")) {
            require(input != null, "version resource");
            properties.load(input);
        }
        require("1.18-zyntax.1".equals(properties.getProperty("version")), "resource identity");
        require(Library.class.getResource("/META-INF/native/android-aarch64/libjansi.so") != null, "Android resource");
        require(Library.class.getResource("/META-INF/native/linux64/libjansi.so") == null, "unexpected Linux resource");
        boolean rejected = false;
        try {
            Library.getPlatform();
        } catch (UnsatisfiedLinkError expected) {
            rejected = expected.getMessage().contains("targets Android aarch64");
        }
        require(rejected, "incompatible x86_64 build host was not rejected");
        require("plain".equals(Ansi.ansi().a("plain").toString()), "source-built ANSI API");
        System.out.println("PASS Java assembly identity, Android resource and truthful incompatible-host rejection");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
