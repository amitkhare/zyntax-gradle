"""Focused source-build JDK selection checks; no Gradle build or network."""

import unittest

from source_java import java_specification_version, javac_version


class JavaVersionOutputTest(unittest.TestCase):
    def test_parses_modern_java_and_javac_versions(self):
        self.assertEqual(11, java_specification_version(
            "Property settings:\n    java.specification.version = 11\nopenjdk version \"11.0.29\"\n"
        ))
        self.assertEqual(25, java_specification_version(
            "    java.specification.version = 25\nopenjdk version \"25\"\n"
        ))
        self.assertEqual(17, javac_version("javac 17.0.16\n"))

    def test_parses_legacy_java_version_form(self):
        self.assertEqual(8, java_specification_version(
            "    java.specification.version = 1.8\n"
        ))
        self.assertEqual(8, javac_version("javac 1.8.0_462\n"))

    def test_rejects_missing_or_ambiguous_java_version(self):
        for output in (
            "openjdk version 17\n",
            "java.specification.version = 17\njava.specification.version = 21\n",
            "java.specification.version = current\n",
        ):
            with self.subTest(output=output), self.assertRaises(ValueError):
                java_specification_version(output)

    def test_rejects_unrecognized_javac_version(self):
        with self.assertRaises(ValueError):
            javac_version("javac current\n")


if __name__ == "__main__":
    unittest.main()
