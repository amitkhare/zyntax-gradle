// SPDX-License-Identifier: Apache-2.0
package org.gradle.internal.logging.sink;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import org.fusesource.jansi.AnsiOutputStream;
import org.fusesource.jansi.internal.CLibrary;
import org.gradle.internal.nativeintegration.jansi.DefaultJansiRuntimeResolver;
import org.gradle.internal.nativeintegration.jansi.JansiBootPathConfigurer;
import org.gradle.internal.nativeintegration.jansi.JansiStorage;
import org.gradle.internal.nativeintegration.jansi.JansiStorageLocator;

/** Checks the selected distribution's real package-private console wrapper in a fresh JVM. */
public final class GradleJansiProbe {
    public static void main(String[] args) throws Exception {
        require(args.length == 1, "Expected one existing app-private work directory");
        require(System.getProperty("library.jansi.path") == null, "Do not override Gradle's library selection");
        require(System.getProperty("jansi.passthrough") == null
                && System.getProperty("jansi.strip") == null
                && System.getProperty("jansi.force") == null, "Do not override Jansi console detection");
        String term = System.getenv("TERM");
        require(term != null && !term.startsWith("xterm"), "Use a non-xterm PTY type such as screen to exercise isatty");
        require("android-aarch64".equals(new DefaultJansiRuntimeResolver().getPlatform()), "Android runtime identity");

        Path run = Files.createTempDirectory(Path.of(args[0]), "gradle-jansi-").toRealPath();
        JansiStorage selected = new JansiStorageLocator().locate(run.toFile());
        require(selected != null, "Gradle must select a Jansi resource");
        Path library = selected.getTargetLibFile().toPath();
        require(library.normalize().startsWith(run), "Extraction must stay inside this probe's directory");
        new JansiBootPathConfigurer().configure(run.toFile());
        require(library.getParent().toString().equals(System.getProperty("library.jansi.path")), "Gradle library path");
        try (InputStream resource = JansiBootPathConfigurer.class.getResourceAsStream(selected.getJansiLibrary().getResourcePath())) {
            require(resource != null && Arrays.equals(resource.readAllBytes(), Files.readAllBytes(library)), "Extracted resource identity");
        }

        // An explicit Gradle-selected path is authoritative in this port; JNI cannot extract elsewhere.
        require(CLibrary.STDOUT_FILENO == 1 && CLibrary.isatty(1) == 1, "Real native stdout PTY");
        CLibrary.WinSize size = new CLibrary.WinSize();
        require(CLibrary.ioctl(1, CLibrary.TIOCGWINSZ, size) == 0 && size.ws_col > 0 && size.ws_row > 0, "Native PTY dimensions");
        byte[] marker = "\u001b[32mGradle Jansi".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream captured = new ByteArrayOutputStream();
        try (OutputStream wrapped = AnsiConsoleUtil.wrapOutputStream(captured)) {
            require(wrapped != captured && !(wrapped instanceof AnsiOutputStream), "Native terminal wrapper, not passthrough or stripping");
            wrapped.write(marker);
        }
        ByteArrayOutputStream expected = new ByteArrayOutputStream();
        expected.write(marker);
        expected.write(AnsiOutputStream.RESET_CODE);
        require(Arrays.equals(expected.toByteArray(), captured.toByteArray()), "Preserved ANSI and reset on close");
        System.out.println("PASS Gradle Jansi runtime wrapper: " + size.ws_col + "x" + size.ws_row + "; " + library);
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
