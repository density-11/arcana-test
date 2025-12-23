basket_prompt = """
Analogy: Lots of objects fall into the basket.
Reason: The 8-grids is the basket, including the handle and the objects itself. The objects are of different colors. The near grids of the same color form an object. There might be different objects. Considering the basket, the basket has a bottom grid, which is the lowest row of grids. Imagine it is a real world process, every object falls into the basket. When the object contacts the bottom, the object will stop, and upper objects will fall on lower objects. The objects pile up in the basket, and are sheltered by original basket that is 8-grids.

Instructions:
    1. You need to parse the basket and the objects first. As is descibed before, 8-cells pattern is the basket, near grids of the same colors are the objects.
    2. Extract the lowest row of the basket as the bottom. Mention, the bigger sequence numbers are the lower grids, which means the input_grid[18][16] is lower than grid[17][16].
    3. Save the original 8-grids to copy in the last procedure.
    4. Write a falling function, the objects will fall due to the gravity. When they contact the bottom of the basket or the lower objects, the objects will stop. The order of falling is from low to high.
    5. Cover the basket on the patterns after executing falling, which is align with the physical world.
"""
bell_prompt = """
Analogy: The wooden stick strick the bell, both of them rotate.
Reason: The 8-grids are wooden stick, and the connected 9-grids is another part of the rotating stick, the end 9-grid is the rotate center. The yellow grids is the bell, and the connected 9-grid is the rotate center. Affected by the gravity, the stick will rotate, and after striking the bell will rotate too. At last, both of them will rotate 90 degree.

Instructions:
    1. Parse the stick and the bell first. Find the two rotate center, they will remain unchanged when rotating. 
    2. In the original input, the bell has a outstanding part in the lowest row which is the clapper of the bell, remember to parse it. Mention, the bigger sequence numbers are the lower grids, which means the input_grid[18][16] is lower than grid[17][16]. And after rotating the clapper will not be on the lowest row, so please parse first.
    3. The clapper will be all of the grids in the lowest row, no matter one or two or more. In physical world, some bell are bigger than the others, so the clapper is bigger than the others.
    2. Decide in which direction will the stick and the bell rotate. You can judge by the relative location of the two or the affect of the gravity on the stick. You must judge the direction in every example, and the stick and the bell will rotate in the same direction.
    3. Write a rotate function, rotate the stick and the bell 90 degrees on the rotating center each.
    4. Attention that the bell has a clapper, when the bell rotate to the final state, the clapper will move down one grid under the gravity. Remember in the phtsical world, an object moves, then the original location will not exist the object.
"""
