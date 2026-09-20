/* SPDX-License-Identifier: Apache-2.0 */
package app.zyntax.gradle.bootstrap;

import java.io.InputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Properties;
import org.gradle.wrapper.Download;
import org.gradle.wrapper.Install;
import org.gradle.wrapper.Logger;
import org.gradle.wrapper.PathAssembler;
import org.gradle.wrapper.WrapperConfiguration;
import org.gradle.wrapper.WrapperExecutor;

/** Installs only. Never loads a project's Wrapper or starts Gradle. */
public final class GradleBootstrap {
    private GradleBootstrap() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 6 || !args[0].equals("--properties")
                || !args[2].equals("--gradle-user-home") || !args[4].equals("--result")) {
            throw new IllegalArgumentException("Usage: GradleBootstrap --properties <absolute file>"
                    + " --gradle-user-home <absolute directory> --result <new absolute JSON file>");
        }
        Path propertiesFile = absolute(args[1]);
        Path gradleUserHome = absolute(args[3]);
        Path result = absolute(args[5]);
        require(Files.isRegularFile(propertiesFile), "Select an extension-owned Wrapper properties file.");
        require(!Files.exists(result) && Files.isDirectory(result.getParent()),
                "The result must be a new file in an existing directory.");

        // The caller writes these properties beside its bootstrap resources, not in the project.
        // Require explicit catalogue identity before the upstream installer can touch its cache.
        Properties properties = new Properties();
        try (InputStream input = Files.newInputStream(propertiesFile)) {
            properties.load(input);
        }
        String checksum = properties.getProperty("distributionSha256Sum", "");
        require(checksum.matches("[0-9a-f]{64}"), "distributionSha256Sum must be an explicit SHA-256.");
        String timeout = properties.getProperty("networkTimeout", "");
        require(timeout.matches("[0-9]+"), "networkTimeout must be explicit positive milliseconds.");
        require(Integer.parseInt(timeout) > 0, "networkTimeout must be positive.");
        require("GRADLE_USER_HOME".equals(properties.getProperty("distributionBase"))
                && "GRADLE_USER_HOME".equals(properties.getProperty("zipStoreBase"))
                && "wrapper/dists".equals(properties.getProperty("distributionPath"))
                && "wrapper/dists".equals(properties.getProperty("zipStorePath")),
                "Use the shared GRADLE_USER_HOME wrapper/dists cache.");
        URI url = new URI(properties.getProperty("distributionUrl", ""));
        require(url.isAbsolute() && ("https".equals(url.getScheme()) || "file".equals(url.getScheme()))
                && url.getUserInfo() == null && url.getQuery() == null && url.getFragment() == null,
                "Use an absolute HTTPS catalogue URL or local file URI without credentials or query parameters.");

        WrapperConfiguration configuration = WrapperExecutor.forWrapperPropertiesFile(propertiesFile.toFile())
                .getConfiguration();
        Logger logger = new Logger(false);
        Install installer = new Install(logger,
                new Download(logger, "Zyntax Gradle bootstrap", "1", configuration.getNetworkTimeout()),
                new PathAssembler(gradleUserHome.toFile(), propertiesFile.getParent().toFile()));
        // Upstream owns cache keys, locking, SHA verification, extraction and the .ok marker.
        Path installation = installer.createDist(configuration).toPath().toAbsolutePath().normalize();
        String json = "{\"schemaVersion\":1,\"wrapperVersion\":\"8.14.3\",\"gradleHome\":"
                + json(installation.toString()) + ",\"gradleUserHome\":" + json(gradleUserHome.toString())
                + ",\"distributionUrl\":" + json(configuration.getDistribution().toASCIIString())
                + ",\"distributionSha256Sum\":" + json(checksum) + "}\n";
        // A caller may consume this only after successful task completion. Never replace a receipt.
        Files.writeString(result, json, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
    }

    private static Path absolute(String value) {
        Path path = Path.of(value);
        require(path.isAbsolute(), "All file and directory arguments must be absolute.");
        return path.normalize();
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalArgumentException(message);
    }

    private static String json(String value) {
        StringBuilder result = new StringBuilder("\"");
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            if (character == '\\' || character == '"') result.append('\\').append(character);
            else if (character < 0x20) result.append(String.format("\\u%04x", (int) character));
            else result.append(character);
        }
        return result.append('"').toString();
    }
}
