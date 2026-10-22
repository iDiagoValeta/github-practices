import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "github-practices"
SKILL = SKILL_DIR / "SKILL.md"

NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FORBIDDEN = {
    "\u2014": "em dash",
    "\u2013": "en dash",
    "\u00b7": "middle dot",
}


def read_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("the file does not start with ---")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("frontmatter without a closing ---") from None

    data = {}
    block = None
    for number, line in enumerate(lines[1:end], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":
            if block is None:
                raise ValueError("line %d: indentation without a parent block" % number)
            key, separator, value = line.strip().partition(":")
            if not separator:
                raise ValueError("line %d: missing ':'" % number)
            data[block][key.strip()] = value.strip().strip("\"'")
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError("line %d: missing ':'" % number)
        key = key.strip()
        value = value.strip().strip("\"'")
        if value:
            data[key] = value
            block = None
        else:
            data[key] = {}
            block = key

    body = "\n".join(lines[end + 1:])
    return data, body


class SkillFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SKILL.read_text(encoding="utf-8")
        cls.data, cls.body = read_frontmatter(cls.text)

    def test_valid_name_matches_the_folder(self):
        name = self.data.get("name", "")
        self.assertRegex(name, NAME_PATTERN)
        self.assertLessEqual(len(name), 64)
        self.assertEqual(name, SKILL_DIR.name)
        self.assertNotIn("claude", name.lower())
        self.assertNotIn("anthropic", name.lower())

    def test_description_present_and_without_angle_brackets(self):
        description = self.data.get("description", "")
        self.assertGreaterEqual(len(description), 1)
        self.assertLessEqual(len(description), 1024)
        self.assertNotIn("<", description)
        self.assertNotIn(">", description)

    def test_license_and_metadata(self):
        self.assertEqual(self.data.get("license"), "MIT")
        metadata = self.data.get("metadata")
        self.assertIsInstance(metadata, dict)
        self.assertEqual(metadata.get("opencode/slash"), "true")

    def test_body_is_short(self):
        lines = len([line for line in self.body.splitlines() if line.strip()])
        self.assertLess(lines, 200)
        self.assertGreater(lines, 0)

    def test_relative_links_exist(self):
        targets = LINK_PATTERN.findall(self.text)
        self.assertTrue(targets)
        for target in targets:
            target = target.strip()
            if target.startswith(("http://", "https://", "mailto:", "#", "${")):
                continue
            path = target.split("#", 1)[0].split("?", 1)[0]
            if not path:
                continue
            with self.subTest(link=target):
                self.assertTrue(
                    (SKILL_DIR / path).exists(),
                    "broken link in SKILL.md: %s" % target,
                )

    def test_no_forbidden_characters(self):
        files = [
            path
            for path in SKILL_DIR.rglob("*")
            if path.is_file() and path.suffix in {".md", ".yml", ".yaml", ".json"}
        ]
        files += [ROOT / "README.md", ROOT / "install.sh"]
        self.assertTrue(files)
        for path in files:
            text = path.read_text(encoding="utf-8")
            for character, name in FORBIDDEN.items():
                with self.subTest(file=str(path), character=name):
                    self.assertNotIn(
                        character,
                        text,
                        "%s contains %s" % (path.relative_to(ROOT), name),
                    )


if __name__ == "__main__":
    unittest.main()
