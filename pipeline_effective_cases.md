# Pipeline Effective Cases

This file records concrete cases where a pipeline module prevented or corrected a failure. Future cases can be appended here.

## Cases

| Case | Module | Effect |
| --- | --- | --- |
| `gear2` | Introspection | Prevented an example-passing but test-wrong program from being accepted after dual-model break checking. |

## Case: gear2

### Summary

In the `gear2` pipeline run, the introspection stage became effective after we changed break checking from a single-model approval to a dual-model approval.

Before the change, a program could pass the example tests, receive a positive break check, and be marked as `pipeline_validated` even when its final test output was wrong. After the change, both Gemini and the main GPT model must judge the program as valid before the pipeline accepts it.

### Before Introspection Worked

Old behavior:

- `code1_gear2.py` passed all examples.
- The break check accepted it as valid.
- The pipeline marked it as `pipeline_validated`.
- Final result was still wrong on the test case.

The underlying code issue was in the contact graph. The program treated gears as adjacent when their bounding boxes touched or overlapped, instead of checking actual colored-cell contact. This caused a false gear connection and therefore an incorrect propagated rotation direction.

Relevant files:

- Program: `core_code/pipeline/programs/GPT5/gear2_2/code1_gear2.py`
- Old flow: `core_code/pipeline/results/GPT5/gear2_2/pipeline_flow_gear2.json`
- Old result: `core_code/pipeline/results/GPT5/gear2_2/result_gear2.json`
- Old rerun flow: `core_code/pipeline/results/GPT5/gear2_2/pipeline_flow_gear2_1.json`
- Old rerun result: `core_code/pipeline/results/GPT5/gear2_2/result_gear2_1.json`

### After Introspection Worked

New behavior:

- `code1_gear2.py` still passed all examples.
- Gemini judged the break check as valid.
- The main GPT model judged the break check as invalid.
- Because both models did not return `True`, the pipeline marked the code as `pipeline_abnormal`.
- The main model instruction identified the real issue: bounding-box adjacency should be replaced with actual colored-cell contact.
- The pipeline then ran `final_rectify`.
- On the next break check, both models returned `True`.
- Final result became correct.

Relevant files:

- New flow: `core_code/pipeline/results/GPT5/gear2_2/pipeline_flow_gear2_2.json`
- New result: `core_code/pipeline/results/GPT5/gear2_2/result_gear2_2.json`
- New log: `core_code/pipeline/logs/GPT5/gear2_2/gear2_test_2.log`
- Program metadata: `core_code/pipeline/programs/GPT5/gear2_2/programs_gear2.json`

### Key Difference

Before:

```text
examples correct -> single break judge True -> pipeline_validated -> wrong test result
```

After:

```text
examples correct -> Gemini True + GPT False -> pipeline_abnormal -> final_rectify -> Gemini True + GPT True -> pipeline_validated -> correct test result
```

This is a concrete example where introspection prevented the pipeline from accepting an example-passing but test-wrong program.
