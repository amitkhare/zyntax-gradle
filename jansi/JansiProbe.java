import java.util.Arrays;
import org.fusesource.jansi.internal.CLibrary;

/** Separate Android-only JNI probe. Running this is a device action, not a build step. */
public final class JansiProbe {
    public static void main(String[] args) {
        require(CLibrary.HAVE_ISATTY && CLibrary.HAVE_TTYNAME, "required native terminal support");
        require(CLibrary.STDOUT_FILENO == 1 && CLibrary.STDERR_FILENO == 2, "native descriptors");
        require(CLibrary.isatty(0) == 1 && CLibrary.isatty(1) == 1, "probe requires a real PTY");
        CLibrary.WinSize terminal = new CLibrary.WinSize();
        require(CLibrary.ioctl(1, CLibrary.TIOCGWINSZ, terminal) == 0, "terminal window size");
        require(terminal.ws_row > 0 && terminal.ws_col > 0, "empty PTY dimensions");

        int[] master = new int[1];
        int[] slave = new int[1];
        CLibrary.WinSize requested = new CLibrary.WinSize((short) 33, (short) 101);
        require(CLibrary.openpty(master, slave, null, null, requested) == 0, "native openpty");
        // These two descriptors belong to this short-lived probe and close on JVM exit.
        require(CLibrary.isatty(master[0]) == 1 && CLibrary.isatty(slave[0]) == 1, "new PTY descriptors");
        require(CLibrary.ttyname(slave[0]) != null, "native ttyname_r");
        CLibrary.WinSize actual = new CLibrary.WinSize();
        require(CLibrary.ioctl(slave[0], CLibrary.TIOCGWINSZ, actual) == 0, "new PTY ioctl");
        require(actual.ws_row == 33 && actual.ws_col == 101, "WinSize JNI layout");

        CLibrary.Termios before = new CLibrary.Termios();
        require(CLibrary.tcgetattr(slave[0], before) == 0, "native tcgetattr");
        require(CLibrary.tcsetattr(slave[0], CLibrary.TCSANOW, before) == 0, "native tcsetattr");
        CLibrary.Termios after = new CLibrary.Termios();
        require(CLibrary.tcgetattr(slave[0], after) == 0, "native termios reread");
        require(before.c_iflag == after.c_iflag && before.c_oflag == after.c_oflag
                && before.c_cflag == after.c_cflag && before.c_lflag == after.c_lflag
                && before.c_line == after.c_line && before.c_ispeed == after.c_ispeed
                && before.c_ospeed == after.c_ospeed && Arrays.equals(before.c_cc, after.c_cc), "Bionic termios round trip");
        System.out.println("PASS Jansi Android JNI: PTY " + terminal.ws_col + "x" + terminal.ws_row
                + ", openpty, ioctl, ttyname and termios; sizes " + CLibrary.WinSize.SIZEOF + "/" + CLibrary.Termios.SIZEOF);
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
