pv_prompt = """
You are a helpful assistant that can solve Abstraction and Reasoning Corpus test. Please answer the given ARC question and give me the most applausible answer. Every question can be analogous to a real world object or physical phenomenon, you are encouraged to use real world rules to solve the question. I will provide you with both the visualization of the question and the matrix, you could think of what it looks like according to the visualization, and then decide the rule to solve the question. In the visualization, every column is an input-output pair, the first row is input and the second row is output. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. And you should answer what object or phenomenon you used to solve the question, use a word or a sentence to describe it. Do NOT include anything other than a json object in your output, answer is your answer, and target is the phenomenon or object.

                    Your output should look like this:
                    {
                    \"answer\":[
                    [[0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0]]
                    ],
                    \"target\": "clock"
                    }"""

npv_prompt = """You are a helpful assistant that can solve Abstraction and Reasoning Corpus test. Please answer the given ARC question and give me the most applausible answer. I will provide you with both the visualization of the question and the matrix, you could decide the rule to solve the question. In the visualization, every column is an input-output pair, the first row is input and the second row is output. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. Do NOT include anything other than a json object in your output, answer is your answer.

                    Your output should look like this:
                    {
                    \"answer\":[
                    [[0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0]]
                    ]
                    }"""

p_prompt = """You are a helpful assistant that can solve Abstraction and Reasoning Corpus test. Please answer the given ARC question and give me the most applausible answer. Every question can be analogous to a real world object or physical phenomenon, you are encouraged to use real world rules to solve the question. I will provide you with the matrix of the question, you could think of what it looks like, and then decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. And you should answer what object or phenomenon you used to solve the question, use a word or a sentence to describe it. Do NOT include anything other than a json object in your output, answer is your answer, and target is the phenomenon or object.

                    Your output should look like this:
                    {
                    \"answer\":[
                    [[0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0]]
                    ],
                    \"target\": "clock"
                    }"""

np_prompt = """You are a helpful assistant that can solve Abstraction and Reasoning Corpus test. Please answer the given ARC question and give me the most applausible answer. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. Do NOT include anything other than a json object in your output, answer is your answer.

                    Your output should look like this:
                    {
                    \"answer\":[
                    [[0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0]]
                    ]
                    }"""

check_prompt = """You are a helpful assistant. There is a dict, which format might be wrong. I expect the format of the dict is a python dict, and the value of the \"answer\" key should be a list. There might be lack of parentheses or comma, please check word by word. Do NOT include anything other than a json object in your output, the output is your rectified dict.


                    Your output should look like this:
                    {
                    \"answer\":[
                    [[0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0,0]]
                    ]
                    }"""
check_p_prompt = """You are a helpful assistant. There is a dict, which format might be wrong. I expect the format of the dict is a python dict, and the value of the \"answer\" key should be a list. There might be lack of parentheses or comma, please check word by word. Do NOT include anything other than a json object in your output, the output is your rectified dict.
"""    


direct_grid_prediction_prompt = """
You are an ARC mechanism simulator. Your job is to use the examples and the analogy context to infer the discrete mechanism, then apply that mechanism directly to the question grid. Do not write code, and do not use any hidden code, code reasoning, or code output.

The examples already include ground-truth outputs, so do not "predict" them. Instead, use them to build and test a reusable mechanism. Keep the reasoning concise but concrete enough to audit.

Requirements:
- Identify movable objects, fixed objects, local/global regions, conserved quantities, interfaces/support/contact, flow/refill/displacement, geometric transforms, or counting/proportional constraints when relevant.
- For each example, trace how the same mechanism maps input objects to output objects. Mention only the key object transitions and checks.
- Before accepting a question prediction, compare the question structure with the example structures. If the question combines repeated, nested, or compositional substructures that were only seen separately or more simply in the examples, consider whether the mechanism should be applied compositionally or recursively to subparts instead of as one global rigid transformation. Different subparts may receive related but different transformations.
- Reject plausible shortcuts when the examples do not prove them. In particular, if a rule may involve interface, support, flow, displacement, conservation, or equilibrium, do not stop at first contact unless the examples prove contact is the stopping rule.
- Apply the mechanism to every question input and return valid output grids only. Each cell must be an integer from 0 to 9, and each output must have the same dimensions as its input.

Return exactly one JSON object:
```json
{
  "Rule_summary": "",
  "Mechanism_spec": {
    "objects": [],
    "invariants": [],
    "update_rule": "",
    "stopping_condition": ""
  },
  "Example_traces": [
    {"index": 0, "object_transitions": [], "checks": []}
  ],
  "Rejected_shortcuts": [],
  "Invariants": [],
  "Transformation_steps": [],
  "Test_trace": {"object_transitions": [], "checks": []},
  "Question_predictions": [
    {"index": 0, "output": [[0]], "confidence": "high | medium | low", "reason": "", "check": ""}
  ],
  "Uncertainty": ""
}
```
"""

direct_grid_arbitration_prompt = """
You are comparing two candidate ARC question outputs after both were generated from the same examples and analogy context.

Candidate A is the output from executable code that passed all examples.
Candidate B is an independent mechanism-grounded direct prediction. Candidate B was asked to infer a reusable mechanism from the examples, trace that mechanism, reject shortcuts, and apply it directly to the question grid.

Your job is not to prefer the direct prediction by default. The code may be correct and the direct prediction may be wrong. Choose "code" if the code output better follows the examples and analogy; choose "direct" if the direct prediction clearly better follows them; choose "uncertain" if there is not enough evidence to trust either candidate.

Do not rely on visual plausibility alone. Compare the rule implied by the examples, the selected expansion concepts, quantitative mechanisms, invariants, and warnings.
Use Candidate B's mechanism trace as evidence, but do not trust it blindly. Reject it if the trace contradicts the examples, ignores an invariant, or overuses vague real-world intuition. Do not prefer Candidate A only because it passed examples; the examples are also visible to Candidate B.

Return exactly one JSON object:
```json
{
  "Preferred": "code | direct | uncertain",
  "Judgement": "True | False",
  "Reason": "",
  "Instructions": ""
}
```
Use Judgement "True" only when Candidate A/code should still be allowed to break. Use Judgement "False" when break should be blocked and the code should be revised.
"""


recog_prompt_head = """
You are a helpful assistant that good at image association. Now I need you to play a role in solving ARC question. I will provide you a picture contains some grids, every column is an input-output pair, the first row is input and the second row is output. Every question can be analogous to objects or phenomenon in real world. Your task is to associate the pattern in the picture with real world, and give me your reason. 
"""
recog_color_tail = """
Please mainly consider the color of the patterns in the examples, use one word or one sentence to describe what the picture looks like in real world, in other words, what can be the picture analogous in real world, and give me your reason.
"""
recog_shape_tail = """
Please mainly consider the shape of the patterns in the examples, use one word or one sentence to describe what the picture looks like in real world, in other words, what can be the picture analogous in real world, and give me your reason.
"""
recog_dynamic_tail = """
Please mainly consider the dynamic change of the patterns in the examples, use one word or one sentence to describe what the rule of the question looks like in real world, in other words, what can be the picture analogous in real world, and give me your reason.
"""
recog_full_tail = """
Please consider the full image of the patterns in the examples, use one word or one sentence to describe what the rule of the question looks like in real world, in other words, what can be the picture analogous in real world, and give me your reason.
"""

recog_prompt_color = recog_prompt_head + recog_color_tail
recog_prompt_shape = recog_prompt_head + recog_shape_tail
recog_prompt_dynamic = recog_prompt_head + recog_dynamic_tail
recog_prompt_full = recog_prompt_head + recog_full_tail

analogy_aspect_output_requirements = """
In addition to the analogy and reason, separately identify:
1. Rule: the overall transformation rule in one concise sentence.
2. Objects: core parsing objects that are necessary for understanding or implementing this task's central rule.

Only include objects that are directly relevant to the core rule. Each object name must be one word or a short phrase of no more than three words. Return at most five objects. Do not include incidental visual elements unless they are important to the rule.

Return exactly one JSON object in the following format:
```json
{
    "Analogy": "",
    "Reason": "",
    "Rule": "",
    "Objects": []
}
```
"""


def build_analogy_aspect_prompt(prompt_tail):
    return (
        recog_prompt_head
        + "\n"
        + prompt_tail.strip()
        + "\n"
        + analogy_aspect_output_requirements.strip()
    )


def build_concept_expansion_prompt_text(structured_json):
    return f"""
You are helping expand analogy concepts for an ARC task.
I will provide structured analogy hypotheses extracted from the task. Each hypothesis may include an analogy, a reason, an overall rule, and core parsing objects. Treat these hypotheses as candidates to examine, not as fixed truths.

Your job is to enrich the concept space before the final slippage step:
1. Propose higher-level category concepts, latent concepts, or domain principles suggested by the rules and objects.
2. Discover useful relationships among the existing objects, such as spatial, temporal, causal, directional, order, symmetry, opposition, containment, or transformation relationships.
3. Propose attached sub-concepts for each important object, meaning components, roles, properties, actions, or fine-grained concepts that naturally belong to that object and could help implement or explain the task.
4. Propose concept mutations: nearby hypotheses that preserve some assumptions from a base hypothesis while changing exactly one core assumption. Use this to avoid only elaborating the current hypothesis.
5. Propose quantitative mechanisms when the hypotheses suggest physical equilibrium, material behavior, force balance, motion, growth, scaling, counting, density, volume, area, distance, time, periodicity, or conservation. These mechanisms should be candidate control parameters that could make the rule executable.

For concept mutations, do not use task-specific rule templates. Work at the level of general assumptions:
- selected entities: which entities are acted on;
- entity relation: how entities are related or grouped;
- operation: what transformation/action is applied;
- reference frame: where the operation is measured or applied;
- control parameter: what determines the amount, direction, count, target, or condition of the operation;
- invariant: what remains unchanged;
- exception: which cases are excluded or treated differently.

Be selective. Prefer concepts that are useful for solving this task's central transformation rule. Avoid generic background concepts and avoid adding incidental visual elements unless they are important to the rule. It is acceptable to propose multiple plausible concept paths, but do not overfit to one path. The examples and matrices are authoritative; if a mutation is more consistent with the examples than the original hypothesis, include it.

Quantitative mechanism requirement:
- Do not force a number when the examples give no evidence for one.
- When a proposed concept could depend on a discrete amount, ratio, threshold, conserved count, repeated unit, or proportional relation, explicitly list it as a candidate mechanism.
- Consider ratios between object size and moved distance, fractions of an object above/below another region, displaced or conserved volume/count, scaling factors, periodic steps, equality relations, and small integer ratios such as half, one third, two thirds, twice, or equal counts.
- State what evidence in the examples would confirm or reject each candidate mechanism.
- Keep these as hypotheses, not final truths.

Diversity requirement for concept mutations:
- Do not let all mutations elaborate the same concept family or the same base hypothesis.
- Prefer mutations that cover different mutated dimensions when the evidence allows it.
- If two mutations are only wording variants of the same idea, merge them and use the slot for a genuinely different neighboring hypothesis.
- Include at least one mutation that changes the operation or reference frame when the examples make such an alternative plausible.
- Include at least one mutation that changes the selected entities, entity relation, control parameter, invariant, or exception when the examples make such an alternative plausible.

Return exactly one JSON object in the following format:
```json
{{
    "Higher_level_concepts": [
        {{
            "Concept": "",
            "Source": [],
            "Reason": ""
        }}
    ],
    "Object_relationships": [
        {{
            "Objects": [],
            "Relation": "",
            "Reason": ""
        }}
    ],
    "Attached_subconcepts": [
        {{
            "Object": "",
            "Subconcepts": [],
            "Reason": ""
        }}
    ],
    "Quantitative_mechanisms": [
        {{
            "Concept": "",
            "Related_objects": [],
            "Candidate_parameter": "",
            "Mechanism": "",
            "Evidence_to_check": []
        }}
    ],
    "Concept_mutations": [
        {{
            "Base_hypothesis": "",
            "Preserved_assumptions": [],
            "Mutated_dimension": "selected_entities | entity_relation | operation | reference_frame | control_parameter | invariant | exception",
            "Mutated_assumption": "",
            "Candidate_concept": "",
            "Why_it_might_help": "",
            "Evidence_to_check": []
        }}
    ]
}}
```

Structured analogy hypotheses:
```json
{structured_json}
```
"""


def build_analogy_composite_prompt_text(aspect_items, concept_expansion_json=None):
    aspect_labels = [
        aspect_config.get("composite_label", aspect_name)
        for aspect_name, aspect_config, _ in aspect_items
    ]
    if len(aspect_labels) == 1:
        aspect_description = aspect_labels[0]
    else:
        aspect_description = ", ".join(aspect_labels[:-1]) + " and " + aspect_labels[-1]

    prompt = f"""
You are a helpful assistant that good at image association. Now I need you to play a role in solving ARC question. I will provide you a picture contains some grids, every column is an input-output pair, the first row is input and the second row is output. Every question can be analogous to objects or phenomenon in real world. Then I will provide you {len(aspect_items)} possible proposals and their reasons, the proposals are about {aspect_description} between input and output respectively. You can combine these proposals and associate new concepts with these proposals, or just choose one of the proposals. Futhermore, you must provide me with the rule in analogy and reason. Give me the top three most possible targets and rules in JSON format.

For each final target, separately identify:
1. Analogy: the real-world analogy target.
2. Reason: why this analogy helps explain the task.
3. Rule: the overall transformation rule in one concise sentence.
4. Objects: core parsing objects that are necessary for understanding or implementing this task's central rule.
5. Used_expansion_concepts: at most six specific concepts selected from the concept expansion that directly support this target.
6. Used_quantitative_mechanisms: at most six selected quantitative mechanisms that could become executable control parameters for this target.
7. Implementation_notes: at most six concise implementation hints implied by the selected expansion. These should be useful for code generation but must still be checked against the examples.
8. Speculative_warnings: at most six plausible but uncertain assumptions that should not be hardcoded unless supported by the examples.

The three final targets should be diverse hypotheses, not near-duplicates. They should preferably come from different concept families or mutate different core assumptions. Before choosing the final targets, compare whether they differ in at least one of these dimensions: selected entities, entity relation, operation, reference frame, control parameter, invariant, or exception. If two targets would lead to nearly the same implementation, keep the stronger one and replace the other with a more different plausible hypothesis.

Only include objects that are directly relevant to the core rule. Each object name must be one word or a short phrase of no more than three words. Return at most five objects for each target. Do not include incidental visual elements unless they are important to the rule.

When concept expansion is provided, do not copy the full expansion into every target. Select only the concepts and quantitative mechanisms that are directly relevant to that target. Keep noisy, weak, or risky expansion ideas in Speculative_warnings rather than Implementation_notes. The examples are authoritative; expansion concepts are candidate hints, not facts.

Your output should look like this:
```json
    {{
        "Analogy_list":[
            {{
                "Analogy": "",
                "Reason": "",
                "Rule": "",
                "Objects": [],
                "Used_expansion_concepts": [],
                "Used_quantitative_mechanisms": [],
                "Implementation_notes": [],
                "Speculative_warnings": []
            }},
            {{
                "Analogy": "",
                "Reason": "",
                "Rule": "",
                "Objects": [],
                "Used_expansion_concepts": [],
                "Used_quantitative_mechanisms": [],
                "Implementation_notes": [],
                "Speculative_warnings": []
            }},
            {{
                "Analogy": "",
                "Reason": "",
                "Rule": "",
                "Objects": [],
                "Used_expansion_concepts": [],
                "Used_quantitative_mechanisms": [],
                "Implementation_notes": [],
                "Speculative_warnings": []
            }}
        ]
    }}
```
"""
    proposal_lines = []
    for index, (aspect_name, aspect_config, proposal) in enumerate(aspect_items, start=1):
        label = aspect_config.get("composite_label", aspect_name)
        proposal_lines.append(
            f"{index}. The analogy mainly considering {label} is: {proposal}\n"
        )
    concept_expansion_section = ""
    if concept_expansion_json:
        concept_expansion_section = f"""

Additional concept expansion generated from the structured rules and objects:
Use this as optional associative context. Prefer expanded concepts that are consistent with the ARC examples and the original proposals; do not blindly copy unsupported concepts. Concept mutations are legitimate candidate directions, not final answers. When producing final targets, include a mutated or neighboring concept if it fits the examples better than simply elaborating the original proposals.
Use the concept mutations to increase diversity among the final three targets. Do not choose three targets that are all refinements of the same mutation or the same base hypothesis unless the examples overwhelmingly rule out alternatives.
Use quantitative mechanisms as candidate executable control parameters when they fit the examples, especially for physical, counting, scaling, periodic, or conservation-based hypotheses. Do not include unsupported numbers just because they are listed as candidates.
For each final target, explicitly select the small subset of expansion concepts and quantitative mechanisms that this target should pass to code generation. Put uncertain or noisy expansion ideas into Speculative_warnings.
```json
{concept_expansion_json}
```
"""
    return prompt + "\n" + "".join(proposal_lines) + concept_expansion_section

recog_com_head = """
You are a helpful assistant that good at image association. Now I need you to play a role in solving ARC question. I will provide you a picture contains some grids, every column is an input-output pair, the first row is input and the second row is output. Every question can be analogous to objects or phenomenon in real world. Then I will provide you four possible proposals and their reasons, the proposals are about color, shape, dynamic change and full image between input and output respectively. You can combine these proposals and associate new concepts with these proposals, or just choose one of the proposals. Furthermore, you must provide me with the analogy, reason, rule, and core parsing objects. Give me the top three most possible targets and rules in JSON format.

Only include objects that are directly relevant to the core rule. Each object name must be one word or a short phrase of no more than three words. Return at most five objects for each target.

Your output should look like this:
```json
    {
        "Analogy_list":[
            {
                "Analogy": "", "Reason": "", "Rule": "", "Objects": []
            },
            {
                "Analogy": "", "Reason": "", "Rule": "", "Objects": []
            },
            {
                "Analogy": "", "Reason": "", "Rule": "", "Objects": []
            }
        ]
    }
```
"""

code_prompt = """
You are a helpful assistant that is good at solving ARC question. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I will provide a possible target and rule from former agent. The rule of the question usually is delicate, which might include moving a parsing region, counting the number of a certain structure, rotating an area, copy some structures that is meaningful, keeping some grids in certain color or number conserved, occlusion relationship, and so on. Therefore I need you to complete a code to execute the rule.

The code should include parsing part and execution part including different functions. In parsing part, the code will locate the target according to some certain rules, for example, according to location, colors and corresponding numbers, shapes, or combination of the possible properties. The parsing group could be a unregular list, which might include some grids that are not necessary to be compared. For example, we use the 10 grids to represent the unnecessarily compared grids because the normal distribution of the grids is 0-9, the parsed object is [[1,1,10,10],[1,1,10,10],[1,1,1,1],[1,1,1,1]] represent a square consisted of 1 but without the upper right 2*2 square. When parsing or moving, the operation should ignore the 10's grids. You may consider more properties according to different question. And when parsing, the pattern in input grids might be sheltered, which means the patterns in input grids and output grids might be part of the full pattern, and you might need to infer where the full patterns are, and use code to accomplish the occlusion relationship. The output of the code might be targets and corresponding point sets. In execution part, you need to use the rule and the parsing sets from parsing part to generate answer grid, input and output are both lists. Sometimes you might need to judge the moving direction step by step, take the falling along the steps as an example, you might need to judge the possible moving direction in every time step for one pattern or grid. It's only an example, you need to judge the algorithm according to different settings.

Code should NOT include ' if '__name__' == 'main' '. The code should only include the functions and a execute function to call these functions, whose name should be execute() to let me call the function easily. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention. Mention that the code should NOT include endless loop.

Please ensure that the dimensions of the input and output are the same. Please do NOT return [output] like this where the output in the square brackets has the same dimension as the input.

I will provide you both the visualization of the question and the matrixs, every column is an input-output pair, the first row is input and the second row is output. Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black. The matrix is a list which might include three or more dicts. Every dict is an example, including input matrix and output matrix.

Please follow this format:

REASONING:
[Think step by step about:
1. Which targets should I consider to represent the rule? I might need to consider multiple targets, and I should consider all of the examples.
2. What characristics should I use to parse the grids and get point sets? Color, shape, location, or combination of above? I should consider the difference on different examples.
3. What algorithm/approach should be used? Move, rotate, mirror, copy a certain structure, or combination of above? I should consider all of the examples.
4. What are the key steps in the implementation? This will guide me to finish the code.]

CODE:
[Your complete, executable Python code here - no markdown formatting]

EXPLANATION:
[Brief explanation of how the code works]
"""

rectify_code_prompt = """
You are a programming assistant. Now I have a execute() function and some small functions. When I call execute(input_list), some error happened. I need you to rectify the code to get the code run successfully. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention. Mention that the code should NOT include endless loop.

I will provide you the code and the error message, please follow this format:
REASONING:
[Think step by step about:
1. What's the reason why the error happens? Did I use a wrong input format?
2. How can I rectify the code?

CODE:
[Your complete, executable Python code here - no markdown formatting]

EXPLANATION:
[Brief explanation of how the code works]
"""

question_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reansoning Corpus (ARC) Test. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I will also provide you a function execute() which is expected to get the output from input. The function is designed to represent the rules of the question. The rules of the question is usually delicate, which might include moving a parsing region, counting the number of a certain structure, rotating an area, copy some structures that is meaningful, keeping some grids in certain color or number conserved, and so on. What I need you to do is to analyze where the function is wrong according to the output of the function and ground truth output.

In this execution, the analogy context of the question might be augmented with sub-concepts attached to the original analogy, rule, or objects, for example, commonsense such as conditions, conservations, time, causality and so on. If the augmentation happens, I will provide the proposals that will direct you to come up with the instructions of modifying code. Please take them into consideration! 

In the following part, I will provide you the analogy context of the question, including Analogy, Reason, Rule, and Objects, the code of the function, explanation of how the code work, the input-output-groudtruth grids picture, the detailed difference grids between output and groudtruth of each example and their coordinates, along with the matrixs of their input, output and groudtruth. 

The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. the explanation is expected to inform how the code works and functions' function. The parsing group could be a unregular list, which might include some grids that are not necessary to be compared. For example, we use the 10 grids to represent the unnecessarily compared grids because the normal distribution of the grids is 0-9, the parsed object is [[1,1,10,10],[1,1,10,10],[1,1,1,1],[1,1,1,1]] represent a square consisted of 1 but without the upper right 2*2 square. When parsing or moving, the operation should ignore the 10's grids. You may consider more properties according to different question. And when parsing, the pattern in input grids might be sheltered, which means the patterns in input grids and output grids might be part of the full pattern, and you might need to infer where the full patterns are, and use code to accomplish the occlusion relationship. In execution part, you need to use the rule and the parsing sets from parsing part to generate answer grid, input and output are both lists. Sometimes you might need to judge the moving direction step by step, take the falling along the steps as an example, you might need to judge the possible moving direction in every time step for one pattern or grid. It's only an example, you need to judge the algorithm according to different settings. 

Input-output-groudtruth picture will include three grids, from left to right lies the input of the function, the output from code, and the groud truth output expected. For detailed comparation, I will provide you with the difference grids picture between output and groundtruth, and the matrixs of input and output and groudtruth. In the difference picture, there will be two grids. The grey grids means the same part of the output and groudtruth, and the other colored part means the different grids between output of the code and groundtruth, including white, blue, teal, orange, green, purple, red, yellow, brown, black. The left grid shows what the code output is in these part, and the right grid shows what the groudtruth is in this part. The coordinates are up to down, left to right, and start from 0. For example, (0,13) means the first rowfrom up to down and the 14th column from left to right.

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Please follow the following format:
REASONING:
[Think step by step about:
1. How does the different parts of the function work? Analyze according to the explanation. 
2. On which input the code generate a wrong output? Why does it generate a wrong output? The problem is on the parsing part or the execution part, or both? I need to analyze all of the examples.
3. Focus on the difference grids, why are these grid wrong? Which part of the code are the main reason causing the difference? Or should I add some rules? If I should add a rule, can I find the corresponding explanation of the target of analogy in real world object or phenomenon?
4. Are algorithm/approach be falsely used or lacked of? Should I add, delete or change the operation of move, rotate, mirror, copy a certain structure, or combination of above? I should consider all of the examples.
5. What are the key steps in the implementation of modifying the function? This will help me instruct the latter agent to modify the code.
]

INSTRUCTIONS:
[The instructions of modifying the code -- try to be comprehensive.]
"""

modify_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reansoning Corpus (ARC) Test. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I will also provide you a wrong function execute() which is expected to get the output from input, and the instructions how to modify the code. The function is designed to represent the rules of the question. The rules of the question is usually delicate, which might include moving a parsing region, counting the number of a certain structure, rotating an area, copy some structures that is meaningful, keeping some grids in certain color or number conserved, and so on. I need you to modify the code to better represent the rules, according to the instructions I provide. Moreover, there might be the modifying instructions of analyzing other better code and the output of the questions, you can consider these instructions according to the circumstances.

In the following part, I will provide you the analogy context of the question, including Analogy, Reason, Rule, and Objects, the code of the function, explanation of how the old code work, the input-output-groudtruth grids picture, along with the matrixs of their input, output and groudtruth. 

Please ensure that the dimensions of the input and output are the same. Please do NOT return [output] like this where the output in the square brackets has the same dimension as the input.

The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. The explanation is expected to inform how the code works and functions' function. The parsing group could be a unregular list, which might include some grids that are not necessary to be compared. For example, we use the 10 grids to represent the unnecessarily compared grids because the normal distribution of the grids is 0-9, the parsed object is [[1,1,10,10],[1,1,10,10],[1,1,1,1],[1,1,1,1]] represent a square consisted of 1 but lost the upper right 2*2 square. When parsing or moving, the operation should ignore the 10's grids. You may consider more properties according to different question. And when parsing, the pattern in input grids might be sheltered, which means the patterns in input grids and output grids might be part of the full pattern, and you might need to infer where the full patterns are, and use code to accomplish the occlusion relationship. The output of the code might be targets and corresponding point sets. In execution part, you need to use the rule and the parsing sets from parsing part to generate answer grid, input and output are both lists. Sometimes you might need to judge the moving direction step by step, take the falling along the steps as an example, you might need to judge the possible moving direction in every time step for one pattern or grid. It's only an example, you need to judge the algorithm according to different settings.

Input-output-groudtruth picture will include three grids, from left to right lies the input of the function, the output from code, and the groud truth output expected. The instructions are generated by the former agent, you can follow the instructions to modify the code. 

Before writing the final code, explicitly check how the provided instructions should be executed. The instructions may come from different agents or different evidence sources, and some of them may be local, partial, ambiguous, or mutually conflicting. Do not silently ignore any instruction. In your reasoning, summarize the actionable instructions, identify whether any instructions conflict or only apply to specific examples/questions, decide which instructions can be implemented consistently, and state how each implemented instruction is reflected in the code. If you decide not to implement an instruction, briefly explain why it is inconsistent, unsupported, or unsafe for the current question.

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Code should NOT include ' if '__name__' == 'main' '. The code should only include the functions and a execute function to call these functions, whose name should be execute() to let me call the function easily. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention. Mention that the code should NOT include endless loop. 

Please follow this format:

REASONING:
[Think step by step about:
1. What are the actionable instructions I received? Are any of them local, partial, ambiguous, or mutually conflicting?
2. Which instructions align with the visualization picture of the examples, the question output, and the analogy context? Which instructions should not be implemented, and why?
3. How can I modify the code to instantiate the instructions that can be implemented consistently? Do I cover every example and avoid the abnormal question output?
4. If the instructions are not clear enough, what algorithms/approaches can I use to instantiate them? Move, rotate, mirror, copy a certain structure, or a combination of the above? I should consider all of the examples.
5. What are the key steps in the implementation of modifying the function? Which functions or code blocks implement each accepted instruction?
]

CODE:
[Your complete, executable Python code here - no markdown formatting]

EXPLANATION:
[Brief explanation of how the code works]
"""

crossover_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reansoning Corpus (ARC) Test. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I have a function execute(), I need to improve the code. To achieve this, I will provide you a better code, you should analyze the advantages of the better code, the disadvantages of the code to be improved, and give me the instructions to improve the code.

In the following part, I will provide you the code to be improved, the analogy context of the code to be improved, the better code and the analogy context of it. Each analogy context includes Analogy, Reason, Rule, and Objects. Besides, I will provide you with the visualization of all of the examples of the question, every column is an input-output pair, the first row is input and the second row is output. The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. The reason and rule are expected to inform you how the code is built and how the code works. 

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Please follow the following format:
REASONING:
[Think step by step about:
1. Analyze these two codes, understand how these two codes work according to the reasons and explanations.
2. Analyze the advantages of the better code, how these advantages are realized, and the details of realization. 
3. Analyze the advantages of the code to be improved, remember to reserve these advantages.
4. Analyze the disadvantages of the better code and the code to be improved, remember to avoid them.
5. What are the key steps in the implementation of modifying the function? This will help me propose the instructions.]

INSTRUCTIONS:
[The instructions of modifying the code -- try to be comprehensive.]
"""

mutate_analogy_prompt = """
You are a helpful assistant that good at image association. Now I need you to play a role in solving ARC question. I will provide you a picture contains some grids, every column is an input-output pair, the first row is input and the second row is output. Every question can be analogous to objects or phenomenon in real world. Then I will provide you a main analogy context, including Analogy, Reason, Rule, and Objects. You should start from this context, associate another analogy context, and explain the reason. Besides, I provide you more analogy contexts. You can combine these proposals and associate new concepts with these proposals, but please mainly consider the main analogy context. Furthermore, you must provide me with the updated analogy, reason, rule, and core parsing objects. Give me ONE most possible target and rule in JSON format.

Do not only elaborate the current analogy. First identify its core assumptions, then create a nearby analogy by preserving some assumptions and mutating one important assumption if that better explains the examples. Use general assumption dimensions: selected entities, entity relation, operation, reference frame, control parameter, invariant, and exception. Avoid task-specific templates; choose the mutation from the evidence in the examples.

Only include objects that are directly relevant to the core rule. Each object name must be one word or a short phrase of no more than three words. Return at most five objects.

Your output should look like this:
```json
{
    "Analogy": "", "Reason": "", "Rule": "", "Objects": []
}
```

"""

mutate_code_prompt = """
You are a helpful assistant that is good at solving ARC question. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I will provide a possible analogy context from former agent, including Analogy, Reason, Rule, and Objects. The rule of the question usually is delicate, which might include moving a parsing region, counting the number of a certain structure, rotating an area, copy some structures that is meaningful, keeping some grids in certain color or number conserved, and so on. Therefore I need you to complete a code to execute the rule. Besides, I will provide you a former analogy context along with its code. Please understand the code and analogy context first, then you can learn from its advantages to construct your code.

The code should include parsing part and execution part including different functions. In parsing part, the code will locate the target according to some certain rules, for example, according to location, colors and corresponding numbers, shapes, or combination of the possible properties. You may consider more properties according to different question. The parsing group could be a unregular list, which might include some grids that are not necessary to be compared. For example, we use the 10 grids to represent the unnecessarily compared grids because the normal distribution of the grids is 0-9, the parsed object is [[1,1,10,10],[1,1,10,10],[1,1,1,1],[1,1,1,1]] represent a square consisted of 1 but lost the upper right 2*2 square. When parsing or moving, the operation should ignore the 10's grids. You may consider more properties according to different question. And when parsing, the pattern in input grids might be sheltered, which means the patterns in input grids and output grids might be part of the full pattern, and you might need to infer where the full patterns are, and use code to accomplish the occlusion relationship. The output of the code might be targets and corresponding point sets. In execution part, you need to use the rule and the parsing sets from parsing part to generate answer grid, input and output are both lists. Sometimes you might need to judge the moving direction step by step, take the falling along the steps as an example, you might need to judge the possible moving direction in every time step for one pattern or grid. It's only an example, you need to judge the algorithm according to different settings.

Code should NOT include ' if '__name__' == 'main' '. The code should only include the functions and a execute function to call these functions, whose name should be execute() to let me call the function easily. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention. Mention that the code should NOT include endless loop.

Please ensure that the dimensions of the input and output are the same. Please do NOT return [output] like this where the output in the square brackets has the same dimension as the input.

I will provide you both the visualization of the question examples and the matrixs, every column is an input-output pair, the first row is input and the second row is output. Besides, I will provide you with a former analogy context and code, remember to understand the advantages and disadvantages of it. Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black. The matrix is a list which might include three or more dicts. Every dict is an example, including input matrix and output matrix.

Please follow this format:

REASONING:
[Think step by step about:
1. Analyze the advantages of the former code, I can learn from these advantages.
2. Analyze the disadvantages of the former code, remember to avoid them.
3. Which targets should I consider to represent the rule? I might need to consider multiple targets, and I should consider all of the examples.
4. What characristics should I use to parse the grids and get point sets? Color, shape, location, or combination of above? I should consider the difference on different examples.
5. What algorithm/approach should be used? Move, rotate, mirror, copy a certain structure, or combination of above? I should consider all of the examples.
6. What are the key steps in the implementation? This will guide me to finish the code.]

CODE:
[Your complete, executable Python code here - no markdown formatting]

EXPLANATION:
[Brief explanation of how the code works]
"""
abnormal_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reansoning Corpus (ARC) Test. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I have already generated a code to compute the output grids of questions, but the code is not accurate right now. I need you to check the outputs of the questions, and compare them with the inputs and outputs of the examples. Please point out the abnormal part of the outputs of the questions, and give me instructions to improve the code.

In the following part, I will provide you the code to be improved and the analogy context of the code to be improved. The analogy context includes Analogy, Reason, Rule, and Objects. Besides, I will provide you with the visualization of all of the examples of the question, every column is an input-output pair, the first row is input and the second row is output. The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. The reason and rule are expected to inform you how the code is built and how the code works.

Besides, I will provide you the visualization of the question input and the corresponding output of the input from the code. In the visualization, the left grid is the question, and the right grid is the output of the code. There is no ground truth. You need to inspect the examples and find the abnormal parts of the output of the question from the code.

Treat the code reasoning and explanation as untrusted claims, not as evidence that the implementation is correct. First infer a mechanism contract independently from the examples and the analogy context. The contract should cover entities and states, relations and dependencies, operation order, control parameters and reference frames, invariants, exceptions, and the lifecycle of each relevant input state. A state may be preserved, transformed, consumed, recomputed, or conditionally preserved. Do not assume that an input state must remain merely because preserving it fits the examples.

Then map every essential contract requirement to concrete code behavior. Mark each requirement as implemented, partially implemented, missing, or contradicted, and use code-level or grid-level evidence. Finally stress-test the implementation against structural changes visible in the question, such as changed relative positions, boundary crossings, counts, nesting or composition, occlusion or overlap, collision, distance, and operation order. These are general audit dimensions, not task-specific rules. Prefer the examples and the independently inferred contract over the current implementation's self-description.

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Please follow the following format:
REASONING:
[Think step by step about:
1. Infer the mechanism contract from the examples and analogy context without trusting the code reasoning.
2. Audit entities, dependencies, operation order, controls, reference frames, invariants, exceptions, and state lifecycles.
3. Map every essential requirement to the implementation and identify missing, partial, or contradictory behavior.
4. Stress-test the code on structural differences in the question and explain any likely abnormal output with concrete evidence.
5. Produce implementation instructions that repair the causal mechanism rather than only patching the visible symptom.]

INSTRUCTIONS:
[The instructions of modifying the code -- try to be comprehensive.]
"""
small_mutation_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reansoning Corpus (ARC) Test. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I will also provide you the existing analogy context, including Analogy, Reason, Rule, and Objects, along with the code which is realized to represent the rule of the analogy. What's more, I visualize the output of the examples inputs from the code and the groundtruth what they are expected to be, and the highlighted difference grids and coordinates of the different grids. I need you to understand the analogy context and code now, and think: Is the analogy context now enough to solve the question? Did I miss some sub-concepts attached to the analogy target or objects, which is important to solving the problem? Should I add the sub-concepts? If I choose to add new sub-concepts, how can I instruct the code modification?

Detailedly description of sub-concepts: there might be latent concepts attached to the objects or phenomenon in the analogy which are not shown in the code and analogy reasons. These may involve conditions, invariants, relations, ordering, reference frames, causes, constraints, or other general assumptions. You need to consider which ones could explain the difference now.

Also consider concept mutation, aligned with the initial slippage process. Do not only add more detail to the current analogy. Identify the current analogy's core assumptions, then decide whether the examples are better explained by preserving some assumptions while changing one important assumption. Use general assumption dimensions: selected entities, entity relation, operation, reference frame, control parameter, invariant, and exception. Avoid task-specific templates; choose the mutation from the evidence in the examples.

If you think that it's neccessary to add some sub-concepts to the existing analogy context, please return your augmented analogy context based on the existing context, and the corresponding proposals to generate the instructions of modifying the code. The proposals should instruct the direction of how to modify the code, so that the latter agents could generate the detailed instructions of modifying the code. 

If you think there's no need to augment the concepts now, just return the existing analogy context I provided to you. And you can return "there's no sub-concepts augmented" in the proposal part. 

In the following part, I will provide you the analogy context of the question, the code of the function, explanation of how the code work, the input-output-groudtruth grids picture, the detailed difference grids between output and groudtruth of each example and their coordinates, along with the matrixs of their input, output and groudtruth. 

The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. the explanation is expected to inform how the code works and functions' function. The parsing group could be a unregular list, which might include some grids that are not necessary to be compared. For example, we use the 10 grids to represent the unnecessarily compared grids because the normal distribution of the grids is 0-9, the parsed object is [[1,1,10,10],[1,1,10,10],[1,1,1,1],[1,1,1,1]] represent a square consisted of 1 but lost the upper right 2*2 square. When parsing or moving, the operation should ignore the 10's grids. You may consider more properties according to different question. And when parsing, the pattern in input grids might be sheltered, which means the patterns in input grids and output grids might be part of the full pattern, and you might need to infer where the full patterns are, and use code to accomplish the occlusion relationship. The output of the code might be targets and corresponding point sets. In execution part, you need to use the rule and the parsing sets from parsing part to generate answer grid, input and output are both lists. Sometimes you might need to judge the moving direction step by step, take the falling along the steps as an example, you might need to judge the possible moving direction in every time step for one pattern or grid. It's only an example, you need to judge the algorithm according to different settings.

Code should NOT include ' if '__name__' == 'main' '. The code should only include the functions and a execute function to call these functions, whose name should be execute() to let me call the function easily. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention. Mention that the code should NOT include endless loop. 

Input-output-groudtruth picture will include three grids, from left to right lies the input of the function, the output from code, and the groud truth output expected. For detailed comparation, I will provide you with the difference grids picture between output and groundtruth, and the matrixs of input and output and groudtruth. In the difference picture, there will be two grids. The grey grids means the same part of the output and groudtruth, and the other colored part means the different grids between output of the code and groundtruth, including white, blue, teal, orange, green, purple, red, yellow, brown, black. The left grid shows what the code output is in these part, and the right grid shows what the groudtruth is in this part. The coordinates are up to down, left to right, and start from 0. For example, (0,13) means the first row from up to down and the 14th column from left to right.

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Please follow this format:

REASONING:
[Think step by step about:
1. Inspect the input-output-groundtruth pictures. On which input the code generate a wrong output? Why does it generate a wrong output? I need to analyze all of the examples.
2. What are the current analogy's core assumptions: selected entities, entity relation, operation, reference frame, control parameter, invariant, and exception?
3. Are there any sub-concepts or concept mutations that can explain the wrong outputs? Are they already realized by the code?
4. Are the sub-concepts or mutations aligned with the examples and the analogy context? If reasonable, how can I augment or mutate the existing analogy context to embody them?
5. I need to give some proposals to instruct the code modifying. I must explain what sub-concepts or mutated assumptions I add which are not realized by the existing code. This will point out the direction for the modification of the code.]

ANALOGY:
{"Analogy": "Your augmented analogy here, based on the existing analogy", "Reason": "Your augmented reasons here, based on the existing reasons", "Rule": "Your augmented or preserved overall rule here", "Objects": []}

PROPOSALS:
[Brief proposals for code modifying, about what you add and which directions to modify the code]
"""
breaking_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reasoning Corpus (ARC) tests. I will provide an analogy context, code reasoning, code explanation, full code, all examples, and question outputs generated by the code. The code passes all examples, but there is no ground truth for the questions. Your task is introspection: determine whether the implementation faithfully realizes a mechanism that generalizes from the examples to the questions.

Do not judge by visual plausibility or by consistency with the code's own explanation. Treat the code reasoning and explanation as untrusted claims. Infer a mechanism contract independently from the examples and the analogy context, then audit the implementation against that contract.

The mechanism contract must cover:
1. entities and states;
2. relations and causal dependencies between them;
3. operation order and intermediate-state dependencies;
4. control parameters and reference frames;
5. invariants and exceptions;
6. the lifecycle of each relevant input state: preserved, transformed, consumed, recomputed, or conditionally preserved.

For every essential contract requirement, identify concrete implementation evidence and classify it as implemented, partially implemented, missing, or contradicted. Do not accept a requirement merely because the code reasoning says it exists. In particular, input copying or retaining old cells is not evidence of an invariant unless the examples support preservation.

Stress-test the candidate on structural differences visible in the questions: changed relative positions, boundary crossings, changed counts, nesting or composition, occlusion or overlap, collision, distance, and operation order. These are general audit dimensions, not assumptions that every task uses all of them. Use only dimensions relevant to the observed data. A test-output concern is blocking only when it is supported by the examples, the independently inferred contract, or a concrete contradiction in the implementation.

Return "True" only when every essential contract requirement is implemented and no evidence-backed blocking issue remains. Consistency between the output and the implementation is not sufficient, because the implementation itself may encode the wrong mechanism. Return "False" when at least one blocking issue is supported by concrete grid-level or code-level evidence.

In the following part, I will provide you the analogy context of the question, the code reasoning, the code explanation, the full code, the visualization and matrix of the examples, and the visualization and matrix of the question input and the corresponding output from the code.

In the visualization of examples, every column is an input-output pair, the first row is input and the second row is output. In the visualization of question input and output from code, the left grid is the question, and the right grid is the output of the code.

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Please follow this format:

REASONING:
[Think step by step about:
1. Infer the mechanism contract independently from the examples and analogy context.
2. Audit state lifecycles and map each essential contract requirement to concrete implementation behavior.
3. Stress-test only the relevant structural differences between examples and questions.
4. Separate evidence-backed blocking issues from speculative concerns, then derive rectification instructions from the blocking issues.]

PROPOSALS:
```json
{
  "Judgement": "True or False",
  "Blocking_issues": [
    {
      "requirement": "The violated mechanism requirement",
      "evidence": "Specific example/grid/code evidence",
      "impact": "How it can invalidate the question output"
    }
  ],
  "Contract_audit": [
    {
      "requirement": "One essential mechanism requirement",
      "status": "implemented, partially implemented, missing, or contradicted",
      "evidence": "Concrete code-level or grid-level evidence"
    }
  ],
  "Question_stress_test": [
    {
      "dimension": "A relevant structural difference",
      "result": "pass, fail, or uncertain",
      "evidence": "Why"
    }
  ],
  "Instructions": "Concrete directions that repair the causal mechanism. Empty when Judgement is True."
}
```
"""
compositional_introspection_prompt = """
You are performing the second, execution-level layer of introspection for an Abstraction and Reasoning Corpus (ARC) candidate. A first-layer semantic audit has already inferred a mechanism contract and tentatively accepted the code. I will provide that audit together with the analogy context, full code, examples, question inputs, and question outputs generated by the code.

Your task is not to repeat the semantic audit. Trace how the implementation composes its local operations on the actual question. A codebase can contain individually plausible parsing, movement, filling, projection, copying, or recoloring functions while still be wrong because an operation is triggered on the wrong component, multiple operations are incorrectly superimposed, operation order hides a defect, or two defects cancel in the final output.

Perform the following general audit:
1. Independently decompose each question into the components and relations that are relevant to changed output cells. Compare this decomposition with the entities produced by the code's parser.
2. For every relevant component, trace the concrete functions, branches, predicates, reference entities, reference frames, and parameters that act on it.
3. State the affected cells or geometric region of every triggered operation as specifically as practical. Function existence is not evidence of correct application.
4. Verify operation eligibility. Explain why this component, orientation, relation, state, or position is allowed to trigger that operation under the first-layer mechanism contract and examples.
5. Audit composition and write order. Identify overlapping operations, repeated application to one component, conflicting reference frames, overwrite precedence, masking, and cases where one erroneous operation hides another.
6. Perform counterfactual isolation. For each material operation, reason about what region would change if that operation were disabled, or if the component were considered alone. Use this to distinguish necessary effects from unsupported additions.
7. Compare composed structures in the question with simpler structures in the examples. Rules that were separately valid in different examples must not be combined automatically without evidence that their triggering conditions can hold simultaneously.

Return "True" only when every material question component triggers only supported operations, all operation overlaps are justified, and no counterfactual check reveals unsupported output cells. Return "False" when a concrete code path applies an operation to an ineligible component, misses a required component, composes operations incompatibly, or relies on cancellation between defects.

Please follow this format:

REASONING:
[Trace component-level execution, operation eligibility, composition, and counterfactual isolation.]

PROPOSALS:
```json
{
  "Judgement": "True or False",
  "Blocking_issues": [
    {
      "requirement": "The violated execution or composition requirement",
      "evidence": "Specific component, code path, predicate, or affected region",
      "impact": "How the composed question output may be invalid"
    }
  ],
  "Component_traces": [
    {
      "component": "A concrete question component or relational group",
      "parsed_as": "How the code represents it",
      "triggered_operations": ["Functions or branches that act on it"],
      "reference": "Reference entity, frame, or parameter",
      "affected_region": "Cells or geometric region affected",
      "eligibility": "supported, unsupported, partial, or uncertain",
      "evidence": "Why"
    }
  ],
  "Overlapping_operations": [
    {
      "component_or_region": "Where operations overlap",
      "operations": ["The overlapping operations"],
      "result": "supported, conflicting, masking, or uncertain",
      "evidence": "Why"
    }
  ],
  "Counterfactual_checks": [
    {
      "change": "Disable one operation or isolate one component",
      "predicted_effect": "Which output region would change",
      "conclusion": "necessary, unsupported, redundant, masking, or uncertain",
      "evidence": "Why"
    }
  ],
  "Instructions": "Concrete directions that repair execution or composition. Empty when Judgement is True."
}
```
"""
final_rectify_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reasoning Corpus (ARC) tests. I will provide an analogy context, including Analogy, Reason, Rule, and Objects, and code that currently passes all examples. However, introspection found an evidence-backed issue in the question output. I will provide instructions and evidence from either a semantic-contract audit or a compositional-execution audit. Please rectify the causal mechanism and its component-level execution in the code, not only the visible output symptom.

In the following part, I will provide you the analogy context of the question, the code of the function, explanation of how the old code work, the visualization of the examples, the matrix of the examples, the visualization of the question input and the corresponding output of the input from the code along with their matrixs.

The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. the explanation is expected to inform how the code works and functions' function. The parsing group could be a unregular list, which might include some grids that are not necessary to be compared. For example, we use the 10 grids to represent the unnecessarily compared grids because the normal distribution of the grids is 0-9, the parsed object is [[1,1,10,10],[1,1,10,10],[1,1,1,1],[1,1,1,1]] represent a square consisted of 1 but lost the upper right 2*2 square. When parsing or moving, the operation should ignore the 10's grids. You may consider more properties according to different question. And when parsing, the pattern in input grids might be sheltered, which means the patterns in input grids and output grids might be part of the full pattern, and you might need to infer where the full patterns are, and use code to accomplish the occlusion relationship. The output of the code might be targets and corresponding point sets. In execution part, you need to use the rule and the parsing sets from parsing part to generate answer grid, input and output are both lists. Sometimes you might need to judge the moving direction step by step, take the falling along the steps as an example, you might need to judge the possible moving direction in every time step for one pattern or grid. It's only an example, you need to judge the algorithm according to different settings.

In the visualization of examples, every column is an input-output pair, the first row is input and the second row is output. In the visualization of question input and output from code, the left grid is the question, and the right grid is the output of the code. The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. the explanation is expected to inform how the code works and functions' function. Considering safety, code do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention. Mention that the code should NOT include endless loop.

Please ensure that the dimensions of the input and output are the same. Please do NOT return [output] like this where the output in the square brackets has the same dimension as the input.

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Please follow this format:

REASONING:
[Think step by step about:
1. Which part are the instructions about? Are they align with the visualization picture of the examples and the analogy?
2. How can I modify the code to instantiate the instructions? Do I cover every examples at the same time rectify the questions?
3. If the instructions are not clear enough, what algorithms/approaches can I use to instantiate the instruction? Move, rotate, mirror, copy a certain structure, or combination of above? I should consider all of the examples and the questions.
4. Will the rectification of the code change the outputs of the examples? The examples are right already now, therefore I don't want them to be changed.
5. What are the key steps in the implementation of modifying the function? This will help me follow the instructions.
]

CODE:
[Your complete, executable Python code here - no markdown formatting]

EXPLANATION:
[Brief explanation of how the code works]
"""
cot_prompt = """

<chain of thought instruction>
Begin by enclosing all thoughts within <thinking> tags, exploring multiple angles and approaches.
Break down the solution into clear steps within <step> tags. Start with a 20-step budget, requesting more for complex problems if needed.
Use <count> tags after each step to show the remaining budget. Stop when reaching 0.
Continuously adjust your reasoning based on intermediate results and reflections, adapting your strategy as you progress.
Regularly evaluate progress using <reflection> tags. Be critical and honest about your reasoning process.
Assign a quality score between 0.0 and 1.0 using <reward> tags after each reflection. Use this to guide your approach:

0.8+: Continue current approach
0.5-0.7: Consider minor adjustments
Below 0.5: Seriously consider backtracking and trying a different approach

If unsure or if reward score is low, backtrack and try a different approach, explaining your decision within <thinking> tags.
For mathematical problems, show all work explicitly using LaTeX for formal notation and provide detailed proofs.
Explore multiple solutions individually if possible, comparing approaches in reflections.
Use thoughts as a scratchpad, writing out all calculations and reasoning explicitly.
</chain of thought instruction>
"""
cotp_prompt = """

<chain of thought instruction>
Begin by enclosing all thoughts within <thinking> tags, exploring multiple angles, analogous targets and approaches.
Break down the solution into clear steps within <step> tags. Start with a 20-step budget, requesting more for complex problems if needed.
Use <count> tags after each step to show the remaining budget. Stop when reaching 0.
Continuously adjust your reasoning based on intermediate results and reflections, adapting your strategy as you progress.
Regularly evaluate progress using <reflection> tags. Be critical and honest about your reasoning process.
Assign a quality score between 0.0 and 1.0 using <reward> tags after each reflection. Use this to guide your approach:

0.8+: Continue current approach
0.5-0.7: Consider minor adjustments
Below 0.5: Seriously consider backtracking and trying a different approach

If unsure or if reward score is low, backtrack and try a different approach, explaining your decision within <thinking> tags.
For mathematical problems, show all work explicitly using LaTeX for formal notation and provide detailed proofs.
Explore multiple solutions individually if possible, comparing approaches in reflections.
Use thoughts as a scratchpad, writing out all calculations and reasoning explicitly.
</chain of thought instruction>
"""
my_cotp_prompt = f"""Think step by step about:
1. What target does the task look like in real world? The target might be some objects or phenomena in real world.
2. What sub-objects are included in the target? In other words, what parts should I parse to solve the task?
3. How can I parse the objects in python? The parsed object might obey the fundation law, such as the near grids of the same color, or in a certain pattern consisted of different colors. You might realize it in your code.
4. How to use the parsed groups to realize the rule? The basic operations might include counting, moving, rotating, calculating, filling, mirroring and so on. For mathematical problems, show all work explicitly using LaTeX for formal notation and provide detailed proofs.
5. Finish your code, evaluate the code and your thinking progress. Be critical and honest about your reasoning process.
6. If you are unsure or you need to augment your analogy target, backtrack and try to fix it.
"""
cot_code_prompt = f"""
You are a helpful assistant that is good at solving the Abstraction and Reasoning Corpus (ARC). Now I will provide you an ARC task, you must think step by step to solve the task. You will be provided with some number of paired example inputs and outputs. The outputs were produced by applying a transformation rule to the inputs. In addition to the paired example inputs and outputs, there is also an additional input without a known output (or possibly multiple additional inputs). Your task is to determine the transformation rule and implement it in code.

The inputs and outputs are each "grids". A grid is a rectangular matrix of integers between 0 and 9 (inclusive). These grids will be shown to you as images and lists. Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Note that in each of these cases, you would need to find the rule by carefully examining the examples and using reasoning. You would then need to implement the transformation rule precisely, taking into account all possible cases and getting all of the details right (e.g., exactly where to place various things or exactly which color to use in each case). If the details aren't fully ironed out, you should do additional reasoning to do so before implementing the transformation in code.

You'll need to carefully reason in order to determine the transformation rule. Start your response by carefully reasoning in <reasoning></reasoning> tags. Then, implement the transformation in code.

Code should NOT include ' if '__name__' == 'main' '. The code should only include the functions and a execute function to call these functions, whose name should be execute() to let me call the function easily. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention.

Please ensure that the dimensions of the input and output are the same. Please do NOT return [output] like this where the output in the square brackets has the same dimension as the input.

Please follow this format:

REASONING:
[{cot_prompt}]

CODE:
[Your complete, executable Python code here - no markdown formatting]
"""
cotp_code_prompt = f"""
You are a helpful assistant that is good at solving the Abstraction and Reasoning Corpus (ARC). Now I will provide you an ARC task, you must think step by step to solve the task. Every task can be analogous to an object or phenomenon in real life. You will be provided with some number of paired example inputs and outputs. The outputs were produced by applying a transformation rule to the inputs. In addition to the paired example inputs and outputs, there is also an additional input without a known output (or possibly multiple additional inputs). Your task is to recognize what object and phenomenon is used in this task, and determine the transformation rule and implement it in code according to the analogous target.

The inputs and outputs are each "grids". A grid is a rectangular matrix of integers between 0 and 9 (inclusive). These grids will be shown to you as images and lists. Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Note that in each of these cases, you would need to find the rule by carefully examining the examples and using reasoning. You would then need to implement the transformation rule precisely, taking into account all possible cases and getting all of the details right (e.g., exactly where to place various things or exactly which color to use in each case). If the details aren't fully ironed out, you should do additional reasoning to do so before implementing the transformation in code.

You'll need to carefully reason in order to determine the transformation rule. Start your response by carefully reasoning in <reasoning></reasoning> tags. Then, implement the transformation in code.

The code should include parsing part and execution part including different functions. In parsing part, the code will locate the target according to some certain rules, for example, according to location, colors and corresponding numbers, shapes, or combination of the possible properties. You may consider more properties according to different question. The output of the code might be targets and corresponding point sets. In execution part, you need to use the rule and the parsing sets from parsing part to generate answer grid, input and output are both lists.

Code should NOT include ' if '__name__' == 'main' '. The code should only include the functions and a execute function to call these functions, whose name should be execute() to let me call the function easily. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention. Mention that the code should NOT include endless loop.

Please ensure that the dimensions of the input and output are the same. Please do NOT return [output] like this where the output in the square brackets has the same dimension as the input.

Please follow this format:

REASONING:
[{my_cotp_prompt}]

CODE:
[Your complete, executable Python code here - no markdown formatting]
"""

baseline_code_prompt = """
Code should NOT include ' if '__name__' == 'main' '. The code should only include the functions and a execute function to call these functions, whose name should be execute() to let me call the function easily. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention. Mention that the code should NOT include endless loop.
"""
baseone_sys_prompt = """
Principles:
    - Avoid ad-hoc exceptions that only fix one example but break generality.
    - If there are multiple tests, your answer could look like: [grid1, grid2]
"""
baseone_sys_prompt_code = """
Principles:
    - Avoid ad-hoc exceptions that only fix one example but break generality.
    - If there are multiple tests, your code should fit all tests. 
"""
basethree_sys_prompt = """
Principles:
    - Avoid ad-hoc exceptions that only fix one example but break generality.
    - You are required to provide the most three possible answers in a list, also known as 'pass@3'. If there is only one test in the task, your answer could look like: {"1": [grid11], "2": [grid12], "3": [grid13]}. And if there are multiple tests, your answer could look like: {"1": [grid11, grid21], "2": [grid12, grid22], "3": [grid13, grid23]}.
    - Guarantee the diversity of the different candidate rules, try to come up with more rules from diverse aspects.
"""
cotone_sys_prompt = """
Principles:
    - Never stop at the first plausible rule; always consider multiple hypotheses.
    - Avoid ad-hoc exceptions that only fix one example but break generality.
    - If there are multiple tests, your answer could look like: [grid1, grid2]
    - Prefer object-based reasoning (connected components, shapes, repetition, symmetry, etc.)
"""
confidence_output_instruction = """CONFIDENCE:
[A single decimal number from 0.0 to 1.0 representing your confidence that the complete final answer for all tests is correct. Do not add explanations in this section.]
"""
cotthree_sys_prompt = """
Principles:
    - Never stop at the first plausible rule; always consider multiple hypotheses.
    - Guarantee the diversity of the different candidate rules, try to come up with more rules from diverse aspects.
    - Avoid ad-hoc exceptions that only fix one example but break generality.
    - You are required to provide the most three possible answers in a list, also known as 'pass@3'. If there is only one test in the task, your answer could look like {"1": [grid11], "2": [grid12], "3": [grid13]}.  And if there are multiple tests, your answer could look like: {"1": [grid11, grid21], "2": [grid12, grid22], "3": [grid13, grid23]}.
    - Prefer object-based reasoning (connected components, shapes, repetition, symmetry, etc.)
"""
cotone_sys_prompt_tail = f"""
Output format:
REASONING:
[Your reasoning progress here, include all of your workflow.]

{confidence_output_instruction}

ANSWER:
[Your answer for all tests - no explanations and no markdown formatting. If there are multiple tests, follow the principles to sequentially place the answers, and your answer shoule be like [grid1, grid2] where grid1 and grid2 are the answers of different questions.]
"""
cotone_sys_prompt_code = """
Principles:
    - Never stop at the first plausible rule; always consider multiple hypotheses.
    - Avoid ad-hoc exceptions that only fix one example but break generality.
    - Prefer object-based reasoning (connected components, shapes, repetition, symmetry, etc.)
"""
cotone_sys_prompt_tail_code = f"""
Output format:
REASONING:
[Your reasoning progress here, include all of your workflow.]

{confidence_output_instruction}

ANSWER:
[Your complete, executable Python code here - no markdown formatting]
"""
baseone_sys_prompt_tail = f"""
Output format:
{confidence_output_instruction}

ANSWER:
[Your answer for all tests - no explanations and no markdown formatting. If there are multiple tests, follow the principles to sequentially place the answers, and your answer shoule be like [grid1, grid2] where grid1 and grid2 are the answers of different questions.]
"""
baseone_sys_prompt_tail_code = f"""
Output format:
{confidence_output_instruction}

ANSWER:
[Your complete, executable Python code here - no markdown formatting]
"""
anacotone_sys_prompt_tail = f"""
Output format:
REASONING:
[Your reasoning progress here, include all of your workflow.]

ANALOGY:
[Your analogous target here, use one word or sentence to describe the rule.]

{confidence_output_instruction}

ANSWER:
[Your answer for all tests - no explanations and no markdown formatting. If there are multiple tests, follow the principles to sequentially place the answers, and your answer shoule be like [grid1, grid2] where grid1 and grid2 are the answers of different questions.]
"""
anaone_sys_prompt_tail = f"""
Output format:
ANALOGY:
[Your analogous target here, use one word or sentence to describe the rule.]

{confidence_output_instruction}

ANSWER:
[Your answer for all tests - no explanations and no markdown formatting. If there are multiple tests, follow the principles to sequentially place the answers, and your answer shoule be like [grid1, grid2] where grid1 and grid2 are the answers of different questions.]
"""
anacotone_sys_prompt_tail_code = f"""
Output format:
REASONING:
[Your reasoning progress here, include all of your workflow.]

ANALOGY:
[Your analogous target here, use one word or sentence to describe the rule.]

{confidence_output_instruction}

ANSWER:
[Your complete, executable Python code here - no markdown formatting]
"""
anaone_sys_prompt_tail_code = f"""
Output format:
ANALOGY:
[Your analogous target here, use one word or sentence to describe the rule.]

{confidence_output_instruction}

ANSWER:
[Your complete, executable Python code here - no markdown formatting]
"""
cotthree_sys_prompt_tail = """
Output format:
REASONING:
[Your reasoning progress here, include all of your workflow.]

ANSWER:
Your answer for all tests - no explanations and no markdown formatting. You need to provide three most possible answers, then use one dict to include all answers, like {"1":[grid11], "2":[grid12], "3":[grid13]}. If there are multiple tests, follow the principles to sequentially place the answers, like [[grid11, grid21], [grid12, grid22], [grid13, grid23]].
"""
basethree_sys_prompt_tail = """
Output format:
ANSWER:
Your answer for all tests - no explanations and no markdown formatting. You need to provide three most possible answers, then use one dict to include all answers, like {"1": [grid11], "2": [grid12], "3":[grid13]}. If there are multiple tests, follow the principles to sequentially place the answers, like {"1": [grid11, grid21], "2": [grid12, grid22], "3": [grid13, grid23]} .
"""
cot_one_sys_prompt_head = """
You are an expert ARC (Abstraction and Reasoning Corpus) task solver. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples.

Your mandatory workflow:
1. Understand:
    - Carefully inspect all training input-output pairs.
    - Describe in words what changes from input to output.

2. Hypothesize:
    - Propose at least two distinct candidate rules that would explain the transformations.
    - For each candidate, give a clear natural language and short pseudocode.
    - Guarantee the diversity of the different candidate rules, try to come up with more rules from diverse aspects.

3. Test:
    - For each cadidate rule, mentally apply it to every training input.
    - Explicitly compare the predicted output with the ground-truth output.
    - Mark each candidate as 'fully consistent', 'partially consistent', or 'inconsistent'.

4. Select:
    - Choose the simplest rule that is fully consistent with all training examples.
    -If none is fully consistent, refine or combine candidates until at least one fits all data.

5.Apply:
    - Apply the selected rule to each test input grid to obtain predicted test outputs.
"""
cot_one_sys_prompt_head_code = """
You are an expert ARC (Abstraction and Reasoning Corpus) task solver. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples.

Your mandatory workflow:
1. Understand:
    - Carefully inspect all training input-output pairs.
    - Describe in words what changes from input to output.

2. Hypothesize:
    - Propose at least two distinct candidate rules that would explain the transformations.
    - For each candidate, give a clear natural language and short pseudocode.
    - Guarantee the diversity of the different candidate rules, try to come up with more rules from diverse aspects.

3. Test:
    - For each cadidate rule, mentally apply it to every training input.
    - Explicitly compare the predicted output with the ground-truth output.
    - Mark each candidate as 'fully consistent', 'partially consistent', or 'inconsistent'.

4. Select:
    - Choose the simplest rule that is fully consistent with all training examples.
    - If none is fully consistent, refine or combine candidates until at least one fits all data.

5. Implementation:
    - Faithfully implement the transformation rule in code to generate the correct answer. 
"""
cot_three_sys_prompt_head = """
You are an expert ARC (Abstraction and Reasoning Corpus) task solver. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples.

Your mandatory workflow:
1. Understand:
    - Carefully inspect all training input-output pairs.
    - Describe in words what changes from input to output.

2. Hypothesize:
    - Propose at least five distinct candidate rules that would explain the transformations.
    - For each candidate, give a clear natural language and short pseudocode.
    - Guarantee the diversity of the different candidate rules, try to come up with more rules from diverse aspects.

3. Test:
    - For each cadidate rule, mentally apply it to every training input.
    - Explicitly compare the predicted output with the ground-truth output.
    - Mark each candidate as 'fully consistent', 'partially consistent', or 'inconsistent'.

4. Select:
    - Choose the simplest three rules that are fully consistent with all training examples.
    - If none is fully consistent, refine or combine candidates until at least one fits all data.

5.Apply:
    - Apply the selected rule to each test input grid to obtain predicted test outputs.
"""
basen_sys_prompt = """
You are an expert ARC (Abstraction and Reasoning Corpus) task solver. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. Please follow the principles and answer the given test.
"""
base_one_sys_prompt_code = """
You are an expert ARC (Abstraction and Reasoning Corpus) task solver. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. Please follow the principles and answer the given test. Your task is to determine the transformation rule and implement it in CODE.
"""
anan_sys_prompt = """
You are an expert ARC (Abstraction and Reasoning Corpus) task solver. Now you will be provided with one ARC task, the rule of the task could be analogous to a target in real life which could be some objects or some natural phenomena. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. Please follow the principles and answer the given test. You are encouraged to use analogy to complete the test.
"""
ana_one_sys_prompt_code = """
You are an expert ARC (Abstraction and Reasoning Corpus) task solver. Now you will be provided with one ARC task, the rule of the task could be analogous to a target in real life which could be some objects or some natural phenomena. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. Please follow the principles and answer the given test. You are encouraged to use analogy to complete the test, and your task is to determine the transformation rule and implement it in CODE. 
"""
anacot_one_sys_prompt_head ="""
You are an expert ARC (Abstraction and Reasoning Corpus) task solver. Now you will be provided with one ARC task, the rule of the task could be analogous to a target in real life which could be some objects or some natural phenomena. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. Please follow the principles and answer the given test.

Your mandatory workflow:
1. Understand:
    - Carefully inspect all training input-output pairs.
    - Describe in workds what changes from input to output.

2. Hypothesize:
    - Propose at least four distinct candidate analogies and their corresponding rules that would explain the transformations.
    - For each candidate, give a clear natural language and short pseudocode.
    - Guarantee the diversity of the different candidate rules, try to come up with more rules from diverse aspects.

3. Test:
    - For each cadidate rule, mentally apply it to every training input.
    - Explicitly compare the predicted output with the ground-truth output.
    - Mark each candidate as 'fully consistent', 'partially consistent', or 'inconsistent'.

4. Select:
    - Choose the simplest rule that is fully consistent with all training examples.
    -If none is fully consistent, refine or combine candidates until at least one fits all data.

5.Apply:
    - Apply the selected rule to each test input grid to obtain predicted test outputs.
"""
anacot_one_sys_prompt_head_code ="""
You are an expert ARC (Abstraction and Reasoning Corpus) task solver. Now you will be provided with one ARC task, the rule of the task could be analogous to a target in real life which could be some objects or some natural phenomena. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. Please follow the principles and answer the given test.

Your mandatory workflow:
1. Understand:
    - Carefully inspect all training input-output pairs.
    - Describe in workds what changes from input to output.

2. Hypothesize:
    - Propose at least four distinct candidate analogies and their corresponding rules that would explain the transformations.
    - For each candidate, give a clear natural language and short pseudocode.
    - Guarantee the diversity of the different candidate rules, try to come up with more rules from diverse aspects.

3. Test:
    - For each cadidate rule, mentally apply it to every training input.
    - Explicitly compare the predicted output with the ground-truth output.
    - Mark each candidate as 'fully consistent', 'partially consistent', or 'inconsistent'.

4. Select:
    - Choose the simplest rule that is fully consistent with all training examples.
    -If none is fully consistent, refine or combine candidates until at least one fits all data.

5. Implementation:
    - Faithfully implement the transformation rule in code to generate the correct answer. 

"""
anacot_three_sys_prompt_head ="""
You are an expert ARC (Abstraction and Reasoning Corpus) task solver. Now you will be provided with one ARC task, the rule of the task could be analogous to a target in real life which could be some objects or some natural phenomena. I will provide you with the matrix of the question, you could decide the rule to solve the question. In matrix, every example is provided as input-output pair, and question is provided as input. There might be multiple questions, they all share the same rule as the examples. Please follow the principles and answer the given test.

Your mandatory workflow:
1. Understand:
    - Carefully inspect all training input-output pairs.
    - Describe in workds what changes from input to output.

2. Hypothesize:
    - Propose at least five distinct candidate analogies and their corresponding rules that would explain the transformations.
    - For each candidate, give a clear natural language and short pseudocode.
    - Guarantee the diversity of the different candidate rules, try to come up with more rules from diverse aspects.

3. Test:
    - For each cadidate rule, mentally apply it to every training input.
    - Explicitly compare the predicted output with the ground-truth output.
    - Mark each candidate as 'fully consistent', 'partially consistent', or 'inconsistent'.

4. Select:
    - Choose the simplest three rules that are fully consistent with all training examples.
    -If none is fully consistent, refine or combine candidates until at least one fits all data.

5.Apply:
    - Apply the selected rule to each test input grid to obtain predicted test outputs.
"""
vision_ex_sys_prompt = """
You will be provided with the visualization of the examples and the questions for better analogy. In the visualization of examples, every column is an input-output pair, the first row is input and the second row is output. From left to right, the columns correspond to example1, example2, and so on. In visualization of questions, there is only one row for the reason that there is no groundtruth. Also, from left to right, the columns correspond to question1, question2, and so on.

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.
"""
base1_sys_prompt = f"""
{basen_sys_prompt}

{baseone_sys_prompt}

{baseone_sys_prompt_tail}
"""
base3_sys_prompt = f"""
{basen_sys_prompt}

{basethree_sys_prompt}

{basethree_sys_prompt_tail}
"""
base1_sys_prompt_code = f"""
{base_one_sys_prompt_code}

{baseline_code_prompt}

{baseone_sys_prompt_code}

{baseone_sys_prompt_tail_code}
"""
cot1_sys_prompt =f"""
{cot_one_sys_prompt_head}

{cotone_sys_prompt}

{cotone_sys_prompt_tail}
"""
cot3_sys_prompt = f"""
{cot_three_sys_prompt_head}

{cotthree_sys_prompt}

{cotthree_sys_prompt_tail}
"""
cot1_sys_prompt_code =f"""
{cot_one_sys_prompt_head_code}

{baseline_code_prompt}

{cotone_sys_prompt_code}

{cotone_sys_prompt_tail_code}
"""
ana1_sys_prompt = f"""
{anan_sys_prompt}

{vision_ex_sys_prompt}

{baseone_sys_prompt}

{anaone_sys_prompt_tail}
"""
ana3_sys_prompt = f"""
{anan_sys_prompt}

{vision_ex_sys_prompt}

{basethree_sys_prompt}

{basethree_sys_prompt_tail}
"""
ana1_sys_prompt_code = f"""
{ana_one_sys_prompt_code}

{vision_ex_sys_prompt}

{baseline_code_prompt}

{baseone_sys_prompt_code}

{anaone_sys_prompt_tail_code}
"""
anacot1_sys_prompt = f"""
{anacot_one_sys_prompt_head}

{vision_ex_sys_prompt}

{cotone_sys_prompt}

{anacotone_sys_prompt_tail}
"""
anacot3_sys_prompt = f"""
{anacot_three_sys_prompt_head}

{vision_ex_sys_prompt}

{cotthree_sys_prompt}

{cotthree_sys_prompt_tail}
"""
anacot1_sys_prompt_code = f"""
{anacot_one_sys_prompt_head_code}

{vision_ex_sys_prompt}

{baseline_code_prompt}

{cotone_sys_prompt_code}

{anacotone_sys_prompt_tail_code}
"""
