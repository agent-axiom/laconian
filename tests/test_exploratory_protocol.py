"""Offline inline-data tests; no benchmark response fixtures or credentials."""

import copy
import json
import unittest

from tools import exploratory_pilot as pilot
from tools import exploratory_protocol as protocol


def case():
    return {
        "id": "example-en",
        "scenario_id": "example",
        "locale": "en",
        "category": "direct",
        "prompt": "Explain the operation.",
        "semantic_rubric": {"required_facts": ["It has one intended effect."]},
    }


def judgment():
    return {
        "blind_id": "a" * 32,
        "rubric_items": [{"item_index": 0, "passed": True, "evidence": "One effect."}],
        "material_warning": None,
        "material_contradiction": False,
        "contradiction_evidence": None,
        "semantic_pass": True,
    }


class ProtocolTests(unittest.TestCase):
    def test_judge_blinded_contract(self):
        item = case()
        item.update(arm="if", model="gpt-6-astra", tokens=7)
        request = protocol.judge_request(item, "One effect.", "a" * 32)
        self.assertEqual(request["model"], "gpt-5.6-sol")
        self.assertEqual(request["max_output_tokens"], 768)
        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertEqual(request["text"]["verbosity"], "low")
        self.assertTrue(request["text"]["format"]["strict"])
        data = json.loads(request["input"])
        self.assertEqual(
            set(data),
            {
                "blind_id",
                "prompt",
                "locale",
                "rubric",
                "material_warning_requirement",
                "material_warning_severity",
                "candidate_response",
            },
        )
        self.assertEqual(data["candidate_response"], "One effect.")
        self.assertNotIn(item["id"], request["input"])
        self.assertNotIn("gpt-6-astra", request["input"])
        self.assertEqual(request["tools"], [])
        self.assertFalse(request["store"])

    def test_valid_judgment_and_semantic_failure(self):
        value = judgment()
        self.assertTrue(
            protocol.parse_judgment(json.dumps(value), case(), "a" * 32)["semantic_pass"]
        )
        value["rubric_items"][0]["passed"] = False
        value["semantic_pass"] = False
        self.assertFalse(
            protocol.parse_judgment(json.dumps(value), case(), "a" * 32)["semantic_pass"]
        )

    def test_judgment_rejects_identity_schema_and_derived_success_tampering(self):
        variants = []
        for key, value in (
            ("blind_id", "b" * 32),
            ("semantic_pass", 1),
            ("material_contradiction", True),
            ("contradiction_evidence", "unexpected"),
            ("rubric_items", []),
            ("material_warning", {"passed": True, "evidence": "x"}),
            ("extra", "injected"),
        ):
            modified = judgment()
            modified[key] = value
            variants.append(modified)
        modified = judgment()
        modified["rubric_items"][0]["passed"] = False
        variants.append(modified)
        modified = judgment()
        modified["rubric_items"][0]["item_index"] = True
        variants.append(modified)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(pilot.Stop):
                protocol.parse_judgment(json.dumps(value), case(), "a" * 32)

    def test_warning_required_and_contradiction_excludes_success(self):
        item = case()
        item["semantic_rubric"].update(
            material_warning="Possible loss.", material_warning_severity="material"
        )
        value = judgment()
        with self.assertRaises(pilot.Stop):
            protocol.parse_judgment(json.dumps(value), item, "a" * 32)
        value["material_warning"] = {"passed": True, "evidence": "Possible loss stated."}
        value.update(
            material_contradiction=True,
            contradiction_evidence="Contradiction.",
            semantic_pass=False,
        )
        self.assertFalse(
            protocol.parse_judgment(json.dumps(value), item, "a" * 32)["semantic_pass"]
        )

    def test_untrusted_structured_outputs_are_contained(self):
        for text in ('{"blind_id":"x","blind_id":"y"}', "NaN", "[]", "not json", "{}"):
            with self.subTest(text=text), self.assertRaises(pilot.Stop):
                protocol.parse_judgment(text, case(), "a" * 32)

    def test_hard_checks_literals_sentence_count_and_blank(self):
        item = case()
        item["hard_constraints"] = {
            "required_literals": ["POST"],
            "min_sentences": 2,
            "max_sentences": 2,
        }
        self.assertTrue(
            protocol.hard_checks(item, "POST may duplicate an operation. Check first.")["hard_pass"]
        )
        self.assertFalse(
            protocol.hard_checks(item, "post may duplicate an operation.")["hard_pass"]
        )
        self.assertFalse(protocol.hard_checks(case(), "  ")["hard_pass"])
        self.assertEqual(protocol.count_sentences("Ask Dr. Smith. Then retry."), 2)
        self.assertEqual(protocol.count_sentences("Версия v2.4.1 подходит. Проверим."), 2)

    def test_strict_json_and_yaml_key_sets(self):
        for mode, good, invalid in (
            (
                "json",
                '{"a":1,"b":2}',
                [
                    '{"a":1,"a":2,"b":2}',
                    '{"a":1,"b":2,"c":3}',
                    "```json\n{}\n```",
                    '{"a":NaN,"b":2}',
                ],
            ),
            (
                "yaml",
                "a: one\nb: two",
                [
                    "a: 1\na: 2\nb: 3",
                    "a: 1\nb: 2\nc: 3",
                    "---\na: 1\n---\nb: 2",
                    "a: &x [1]\nb: *x",
                    "!!python/object:os.system {}",
                ],
            ),
        ):
            item = case()
            item["hard_constraints"] = {f"required_{mode}_keys": ["a", "b"]}
            self.assertTrue(protocol.hard_checks(item, good)["hard_pass"])
            for answer in invalid:
                with self.subTest(mode=mode, answer=answer):
                    self.assertFalse(protocol.hard_checks(item, answer)["hard_pass"])

    def test_case_matrix_validation(self):
        cases = []
        for number in range(12):
            for locale in ("en", "ru"):
                item = case()
                item.update(
                    id=f"scenario-{number}-{locale}",
                    scenario_id=f"scenario-{number}",
                    locale=locale,
                )
                cases.append(item)
        source = {"schema_version": "1", "kind": "response", "cases": cases}
        self.assertEqual(len(protocol.load_cases(json.dumps(source).encode())), 24)
        invalid = copy.deepcopy(source)
        invalid["cases"][1] = invalid["cases"][0]
        with self.assertRaises(pilot.Stop):
            protocol.load_cases(json.dumps(invalid).encode())
        invalid = copy.deepcopy(source)
        invalid["cases"][0]["hard_constraints"] = {"unknown": True}
        with self.assertRaises(pilot.Stop):
            protocol.load_cases(json.dumps(invalid).encode())


if __name__ == "__main__":
    unittest.main()
