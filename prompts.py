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

recog_com_head = """
You are a helpful assistant that good at image association. Now I need you to play a role in solving ARC question. I will provide you a picture contains some grids, every column is an input-output pair, the first row is input and the second row is output. Every question can be analogous to objects or phenomenon in real world. Then I will provide you four possible proposals and their reasons, the proposals are about color, shape, dynamic change and full image between input and output respectively. You can combine these proposals and associate new concepts with these proposals, or just choose one of the proposals. Futhermore, you must provide me with the rule in analogy and reason. Give me the top three most possible targets and rules in JSON format.

Your output should look like this:
    {
        "Analogy_list":[
            {
                "Analogy": "", "Reason": ""
            },
            {
                "Analogy": "", "Reason": ""
            },
            {
                "Analogy": "", "Reason": ""
            }
        ]
    }
"""

code_prompt = """
You are a helpful assistant that is good at solving ARC question. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I will provide a possible target and rule from former agent. The rule of the question usually is delicate, which might include moving a parsing region, counting the number of a certain structure, rotating an area, copy some structures that is meaningful, keeping some grids in certain color or number conserved, and so on. Therefore I need you to complete a code to execute the rule.

The code should include parsing part and execution part including different functions. In parsing part, the code will locate the target according to some certain rules, for example, according to location, colors and corresponding numbers, shapes, or combination of the possible properties. You may consider more properties according to different question. The output of the code might be targets and corresponding point sets. In execution part, you need to use the rule and the parsing sets from parsing part to generate answer grid, input and output are both lists.

Code should NOT include ' if '__name__' == 'main' '. The code should only include the functions and a execute function to call these functions, whose name should be execute() to let me call the function easily. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention.

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
You are a programming asssistant. Now I have a execute() function and some small functions. When I call execute(input_list), some error happened. I need you to rectify the code to get the code run successfully. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention.

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

In this execution, the analogy of the question might be augmented with the sub-concepts attached to the original analogy, for example, commonsense such as conditions, conservations, time, causality and so on. If the augmentation happens, I will provide the proposals that will direct you to come up with the instructions of modifying code. Please take them into consideration! 

In the following part, I will provide you the analogy of the question, the code of the function, explanation of how the code work, the input-output-groudtruth grids picture, the detailed difference grids between output and groudtruth of each example and their coordinates, along with the matrixs of their input, output and groudtruth. 

The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. the explanation is expected to inform how the code works and functions' function. Input-output-groudtruth picture will include three grids, from left to right lies the input of the function, the output from code, and the groud truth output expected. For detailed comparation, I will provide you with the difference grids picture between output and groundtruth, and the matrixs of input and output and groudtruth. In the difference picture, there will be two grids. The grey grids means the same part of the output and groudtruth, and the other colored part means the different grids between output of the code and groundtruth, including white, blue, teal, orange, green, purple, red, yellow, brown, black. The left grid shows what the code output is in these part, and the right grid shows what the groudtruth is in this part. The coordinates are up to down, left to right, and start from 0. For example, (0,13) means the first rowfrom up to down and the 14th column from left to right.

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

In the following part, I will provide you the analogy of the question, the code of the function, explanation of how the old code work, the input-output-groudtruth grids picture, along with the matrixs of their input, output and groudtruth. 

Please ensure that the dimensions of the input and output are the same. Please do NOT return [output] like this where the output in the square brackets has the same dimension as the input.

The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. The explanation is expected to inform how the code works and functions' function. Input-output-groudtruth picture will include three grids, from left to right lies the input of the function, the output from code, and the groud truth output expected. The instructions are generated by the former agent, you can follow the instructions to modify the code. 

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Code should NOT include ' if '__name__' == 'main' '. The code should only include the functions and a execute function to call these functions, whose name should be execute() to let me call the function easily. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention.

Please follow this format:

REASONING:
[Think step by step about:
1. Which part are the instructions about? Are they align with the visualization picture of the examples and the analogy?
2. How can I modify the code to instantiate the instructions? Do I cover every examples?
3. If the instructions are not clear enough, what algorithms/approaches can I use to instantiate the instruction? Move, rotate, mirror, copy a certain structure, or combination of above? I should consider all of the examples.
4. What are the key steps in the implementation of modifying the function? This will help me follow the instructions.
]

CODE:
[Your complete, executable Python code here - no markdown formatting]

EXPLANATION:
[Brief explanation of how the code works]
"""

crossover_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reansoning Corpus (ARC) Test. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I have a function execute(), I need to improve the code. To achieve this, I will provide you a better code, you should analyze the advantages of the better code, the disadvantages of the code to be improved, and give me the instructions to improve the code.

In the following part, I will provide you the code to be improved, the analogy and reason of the code to be improved, the better code and the analogy and reason of it. Besides, I will provide you with the visualization of all of the examples of the question, every column is an input-output pair, the first row is input and the second row is output. The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. The reason is expected to inform you how the code is built and how the code works. 

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
You are a helpful assistant that good at image association. Now I need you to play a role in solving ARC question. I will provide you a picture contains some grids, every column is an input-output pair, the first row is input and the second row is output. Every question can be analogous to objects or phenomenon in real world. Then I will provide you a main analogy and its reason. You should start from this analogy and its reason, associate another analogy and explain the reason. Besides, I provide you more analogies and their reasons.  You can combine these proposals and associate new concepts with these proposals, but please mainly consider the main analogy. Futhermore, you must provide me with the rule in analogy and reason. Give me ONE most possible targets and rules in JSON format.

Your output should look like this:
{
    "Analogy": "", "Reason": ""
}

"""

mutate_code_prompt = """
You are a helpful assistant that is good at solving ARC question. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I will provide a possible target and rule from former agent. The rule of the question usually is delicate, which might include moving a parsing region, counting the number of a certain structure, rotating an area, copy some structures that is meaningful, keeping some grids in certain color or number conserved, and so on. Therefore I need you to complete a code to execute the rule. Besides, I will provide you a former analogy along with its reason and code. Please understand the code and analogy first, then you can learn from its advantages to construct your code.

The code should include parsing part and execution part including different functions. In parsing part, the code will locate the target according to some certain rules, for example, according to location, colors and corresponding numbers, shapes, or combination of the possible properties. You may consider more properties according to different question. The output of the code might be targets and corresponding point sets. In execution part, you need to use the rule and the parsing sets from parsing part to generate answer grid, input and output are both lists.

Code should NOT include ' if '__name__' == 'main' '. The code should only include the functions and a execute function to call these functions, whose name should be execute() to let me call the function easily. The input should be a list, and output should be a list, that is, the function should be 'def execute(input_list : list) -> list'. Considering safety, do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention.

Please ensure that the dimensions of the input and output are the same. Please do NOT return [output] like this where the output in the square brackets has the same dimension as the input.

I will provide you both the visualization of the question examples and the matrixs, every column is an input-output pair, the first row is input and the second row is output. Besides, I will provide you with a former analogy along with its reason and code, remember to understand the advantages and disadvantages of it. Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black. The matrix is a list which might include three or more dicts. Every dict is an example, including input matrix and output matrix.

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

In the following part, I will provide you the code to be improved, the analogy and reason of the code to be improved. Besides, I will provide you with the visualization of all of the examples of the question, every column is an input-output pair, the first row is input and the second row is output. The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. The reason is expected to inform you how the code is built and how the code works.

Besides, I will provide you the visualization of the question input and the corresponding output of the input from the code. In the visualization, the left grid is the question, and the right grid is the output of the code. There is no ground truth. You need to inspect the examples and find the abnormal parts of the output of the question from the code.

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Please follow the following format:
REASONING:
[Think step by step about:
1. Inspect the examples, check the input-output pairs, compare them with the analogy and reason I provide.
2. Check the inputs and outputs of the questions from the code. Are there any parts that are abnormal? 
3. Check the code and code reasoning. How can I improve the codes to avoid the abnormal parts?
4. Should I introduce more sub-concepts attached to the analogy to generate better and less abnormal results.
5. What are the key steps in the implementation of modifying the function? This will help me propose the instructions.]

INSTRUCTIONS:
[The instructions of modifying the code -- try to be comprehensive.]
"""
small_mutation_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reansoning Corpus (ARC) Test. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Besides, I will also provide you the existing analogy and the corresponding reason, along with the code which is realized to represent the rule of the analogy. What's more, I visualize the output of the examples inputs from the code and the groundtruth what they are expected to be, and the highlighted difference grids and coordinates of the different grids. I need youto understand the analogy and code now, and think: Is the analogy now is enough to solve the question? Did I miss some sub-concepts attached to the analogy target now, which is important to solving the problem? Should I add the sub-concepts? If I choose to add new sub-concepts, how can I instruct the code modification?

Detailedly description of sub-concepts: there might be some laws of the physics attached to the objects or phenonmenon in the analogy, which is not shown in the code and analogy reasons. For example, commonsense such as conditions, conservations, time, causality etc. You need to consider which one you could add to explain the difference now.

If you think that it's neccessary to add some sub-concepts to the existing analogy, please return your augmented analogy and corresponding augmented reason based on the existing analogy, and the corresponding proposals to generate the instructions of modifying the code. The proposals should instruct the direction of how to modify the code, so that the latter agents could generate the detailed instructions of modifying the code. 

If you think there's no need to augment the concepts now, just return the existing analogy and its reasons I provided to you. And you can return "there's no sub-concepts augmented" in the proposal part. 

In the following part, I will provide you the analogy of the question, the code of the function, explanation of how the code work, the input-output-groudtruth grids picture, the detailed difference grids between output and groudtruth of each example and their coordinates, along with the matrixs of their input, output and groudtruth. 

The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. the explanation is expected to inform how the code works and functions' function. Input-output-groudtruth picture will include three grids, from left to right lies the input of the function, the output from code, and the groud truth output expected. For detailed comparation, I will provide you with the difference grids picture between output and groundtruth, and the matrixs of input and output and groudtruth. In the difference picture, there will be two grids. The grey grids means the same part of the output and groudtruth, and the other colored part means the different grids between output of the code and groundtruth, including white, blue, teal, orange, green, purple, red, yellow, brown, black. The left grid shows what the code output is in these part, and the right grid shows what the groudtruth is in this part. The coordinates are up to down, left to right, and start from 0. For example, (0,13) means the first rowfrom up to down and the 14th column from left to right.

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Please follow this format:

REASONING:
[Think step by step about:
1. Inspect the input-output-groundtruth pictures. On which input the code generate a wrong output? Why does it generate a wrong output? I need to analyze all of the examples.
2. Are there any sub-concepts attached to the existing analogy and reasons that I can use to explain the wrong outputs? Are they already realized by the code?
3. Are the sub-concepts I find align with the objects and the phenonmenon in real world in the existing analogy? If reasonable, how can I augment the existing analogy and its reason to embody the sub-concepts?
4. I need to give some proposals to instruct the code modifying. I must explain what sub-concepts I add which is not realized by the existing code. This will point out the direction for the modification of the code.]

ANALOGY:
{"Analogy": "Your augmented analogy here, based on the existing analogy", "Reason": "Your augmented reasons here, also based on the existing reasons"}

PROPOSALS:
[Brief proposals for code modifying, about what you add and which directions to modify the code]
"""
breaking_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reansoning Corpus (ARC) Test. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Now I will provide you the analogy of the question along with its reason. The code of which has been finished, and after testing I find that the code is right on all examples. However, I need you to judge whether the question output from the code is right or not. Mention that there is no groudtruth for question, what you need to consider is whether the output of the question from the code is normal or not. If the output does not align with the analogy or examples I provide, please give me the signal, and provide the instruction about how to improve the code, where should I pay attention.

In judging dict you should return, there will be two keys: "Judgement" and "Instructions". The value of "Judgement" should ONLY be "True" or "False", no other things. If the "Judgement" you give me is "False", please provide the "Instructions" how I should improve the code; if not, the "Instructions" can be anything.

In the following part, I will provide you the analogy of the question along with its reason, the visualization of the examples, the visualization of the question input and the corresponding output of the input from the code.

In the visualization of examples, every column is an input-output pair, the first row is input and the second row is output. In the visualization of question input and output from code, the left grid is the question, and the right grid is the output of the code.

Relation between the color and the number is provided: 0: white, 1: blue, 2: teal, 3: orange, 4: green, 5: purple, 6: red, 7: yellow, 8: brown, 9: black.

Please follow this format:

REASONING:
[Think step by step about:
1. Understand the analogy and its reason of the problem. How can it align with the examples?
2. Inspect the question input and the output generated by the code. Is there something abnormal? Or not align with the examples and analogy?
3. If there is something weired, please point out and give me some instructions to rectify.]

PROPOSALS:
{"Judgement": "True or False", "Instructions": "Your instructions here, guiding me the directions of consideration."}
"""
final_rectify_code_prompt = """
You are a helpful assistant that is good at solving Abstraction and Reansoning Corpus (ARC) Test. Now I will provide you an ARC question, the question can be analogous to objects or phenomenon in real world. Now I will provide you the analogy of the question along with its reason. The code of which has been finished, and after testing I find that the code is right on all examples. However, when the code is executed on questions, I find something weired, where is not align with the examples and the analogy. Also I will provide you the instructions of the directions how to improve the code. Please rectify the code.

In the following part, I will provide you the analogy of the question, the code of the function, explanation of how the old code work, the visualization of the examples, the matrix of the examples, the visualization of the question input and the corresponding output of the input from the code along with their matrixs.

In the visualization of examples, every column is an input-output pair, the first row is input and the second row is output. In the visualization of question input and output from code, the left grid is the question, and the right grid is the output of the code. The code includes parsing part and execution part, and at last I will call execute(input: list) -> list to get my output. the explanation is expected to inform how the code works and functions' function. Considering safety, code do NOT include 'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'. Input matrix will ALWAYS be one input which is a two-dimention list. A possible input is: [[1, 0], [0, 1]], please pay attention.

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
cot_code_prompt = """
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
