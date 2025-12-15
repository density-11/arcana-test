import numpy as np
from openai import OpenAI
import base64
import json
import os
import glob
from tqdm import tqdm

import ipdb

def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def test_recog_target(image_path):
    client = OpenAI()
    base64_image = encode_image_to_base64(image_path)
    ex_path = "./onlypic/lock1.png"
    lock_image = encode_image_to_base64(image_path)
    example_prompt = "An example is provided as the first image, the answer is lock. Please answer the second image."
    try:
        response = client.chat.completions.create(
                model = "gpt-5-2025-08-07",
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": """You are a helpful assistant that is good at ARC questions, I will give you a picture of one ARC questions, every column is an input-output pair, the first row is input and the second row is output. Please use one word or sentence to describe what the picture looks like in real world, in other word, what can be the rule analogous to in the real world. Do NOT include anything other than the word or sentence.

                                """},
#                            {
#                                "type": "image_url", "image_url": {"url": f"data:image/png;base64,{lock_image}"}
#                                },
                            {
                                "type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                                }
                            ]
                        }
                    ]
                )
    except:
        print("Error!")
        return None

    return response.choices[0].message.content


if __name__ == "__main__":
    data_path = "./onlypic"
    pattern = os.path.join(data_path, "*.png")
    pics = sorted(glob.glob(pattern))
    recog_dict = {}
    temp_count = 0
    while len(pics) != 0:
        failed_pics = []
        for pic in tqdm(pics):
            ans_recog = test_recog_target(pic)
            if ans_recog is None:
                failed_pics.append(pic)
                continue

            pic_name = pic.replace("./onlypic", "").replace(".png", "")
            recog_dict[pic_name] = ans_recog
            temp_count +=1
        print(failed_pics)
        pics = failed_pics
        if len(pics) != 0:
            print("Now test the failed pictures.")

    with open("gpt5_VL_recog.json", "w") as f:
        json.dump(recog_dict, f)


