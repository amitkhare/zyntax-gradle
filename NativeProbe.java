import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Collections;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import net.rubygrapefruit.platform.Native;
import net.rubygrapefruit.platform.SystemInfo;
import net.rubygrapefruit.platform.file.FileInfo;
import net.rubygrapefruit.platform.file.FileSystems;
import net.rubygrapefruit.platform.internal.Platform;
import net.rubygrapefruit.platform.internal.jni.NativeLibraryFunctions;
import net.rubygrapefruit.platform.internal.jni.TerminfoFunctions;
import net.rubygrapefruit.platform.terminal.TerminalOutput;
import net.rubygrapefruit.platform.terminal.TerminalSize;
import net.rubygrapefruit.platform.terminal.Terminals;
import org.gradle.fileevents.FileEvents;
import org.gradle.fileevents.FileWatchEvent;
import org.gradle.fileevents.FileWatcher;
import org.gradle.fileevents.internal.AbstractNativeFileEventFunctions;
import org.gradle.fileevents.internal.LinuxFileEventFunctions;

/** Standalone component probe; never reads or changes an installed Gradle tree. */
public final class NativeProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("Expected one app-private work directory");
        Path root = new File(args[0]).toPath().toAbsolutePath();
        java.nio.file.Files.createDirectories(root);
        Path run = java.nio.file.Files.createTempDirectory(root, "run-");
        File extract = run.resolve("native").toFile();
        if (!Platform.current().getId().equals("android-aarch64")) throw new AssertionError("Wrong target identity");
        Native nativeApi = Native.init(extract);
        SystemInfo system = nativeApi.get(SystemInfo.class);
        System.out.println("native-platform=" + NativeLibraryFunctions.getVersion());
        System.out.println("platform=" + Platform.current().getId() + " kernel=" + system.getKernelName()
            + " arch=" + system.getArchitectureName());
        int mounts = nativeApi.get(FileSystems.class).getFileSystems().size();
        if (mounts == 0) throw new AssertionError("No native file-system records");
        System.out.println("native-filesystems=" + mounts);
        Terminals terminals = nativeApi.get(Terminals.class);
        if (!TerminfoFunctions.getVersion().equals(NativeLibraryFunctions.getVersion())) throw new AssertionError("Curses version mismatch");
        if (!terminals.isTerminal(Terminals.Output.Stdout)) throw new AssertionError("Terminal probe requires stdout attached to a PTY");
        TerminalOutput terminal = terminals.getTerminal(Terminals.Output.Stdout);
        TerminalSize size = terminal.getTerminalSize();
        if (size.getCols() <= 0 || size.getRows() <= 0) throw new AssertionError("PTY window size must be nonzero");
        if (!terminal.supportsColor() || !terminal.supportsTextAttributes() || !terminal.supportsCursorMotion()) {
            throw new AssertionError("Probe requires a color terminal with text attributes and cursor motion");
        }
        System.out.println("terminal=" + terminal + " size=" + size.getCols() + "x" + size.getRows()
            + " stdin-tty=" + terminals.isTerminalInput() + " curses=" + TerminfoFunctions.getVersion());
        net.rubygrapefruit.platform.file.Files files = nativeApi.get(net.rubygrapefruit.platform.file.Files.class);
        Path watched = java.nio.file.Files.createDirectory(run.resolve("watched"));
        if (files.stat(watched.toFile()).getType() != FileInfo.Type.Directory) throw new AssertionError("Native directory stat failed");

        BlockingQueue<FileWatchEvent> events = new LinkedBlockingQueue<>();
        FileEvents fileEvents = FileEvents.init(extract);
        System.out.println("file-events=" + AbstractNativeFileEventFunctions.getVersion());
        FileWatcher watcher = fileEvents.get(LinuxFileEventFunctions.class).newWatcher(events).start();
        try {
            watcher.startWatching(Collections.singleton(watched.toFile()));
            Path marker = watched.resolve("probe.txt");
            byte[] contents = "Android JNI probe\n".getBytes(StandardCharsets.UTF_8);
            java.nio.file.Files.write(marker, contents);
            FileInfo info = files.stat(marker.toFile());
            if (info.getType() != FileInfo.Type.File || info.getSize() != contents.length) throw new AssertionError("Native file stat failed");
            if (files.listDir(watched.toFile()).size() != 1) throw new AssertionError("Native readdir failed");
            await(events, FileWatchEvent.ChangeType.CREATED, marker.toFile().getAbsolutePath());
            java.nio.file.Files.delete(marker);
            await(events, FileWatchEvent.ChangeType.REMOVED, marker.toFile().getAbsolutePath());
            if (!watcher.stopWatching(Collections.singleton(watched.toFile()))) throw new AssertionError("Unwatch failed");
        } finally {
            watcher.shutdown();
            if (!watcher.awaitTermination(5, TimeUnit.SECONDS)) throw new AssertionError("Watcher shutdown timed out");
        }
        System.out.println("PASS native load/version, curses/terminfo/PTY, stat/readdir/mounts, inotify create/remove/shutdown; work=" + run);
    }

    private static void await(BlockingQueue<FileWatchEvent> events, FileWatchEvent.ChangeType type, String path) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        final boolean[] matched = { false };
        FileWatchEvent.Handler handler = new FileWatchEvent.Handler() {
            public void handleChangeEvent(FileWatchEvent.ChangeType actual, String actualPath) {
                if (actual == type && actualPath.equals(path)) matched[0] = true;
            }
            public void handleUnknownEvent(String actualPath) { throw new AssertionError("Unknown event: " + actualPath); }
            public void handleOverflow(FileWatchEvent.OverflowType source, String actualPath) { throw new AssertionError("Event overflow: " + source); }
            public void handleFailure(Throwable failure) { throw new AssertionError("Watcher failed", failure); }
            public void handleTerminated() { throw new AssertionError("Watcher terminated before expected event"); }
        };
        while (!matched[0]) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) throw new AssertionError("Missing event " + type + " for " + path);
            FileWatchEvent event = events.poll(remaining, TimeUnit.NANOSECONDS);
            if (event == null) throw new AssertionError("Missing event " + type + " for " + path);
            event.handleEvent(handler);
        }
        System.out.println("event=" + type + " path=" + path);
    }
}
