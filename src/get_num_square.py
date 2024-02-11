# src/get_num_square.py
import os

# get the input and convert it to int
num = os.environ.get("INPUT_NUM")
if num:
    try:
        num = int(num)
    except Exception:
        exit('ERROR: the INPUT_NUM provided ("{}") is not an integer'.format(num))
else:
    num = 1


with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
    f.write(f"num_squared={num ** 2}\n")
