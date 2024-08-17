import os
import string
import pandas as pd
from datetime import datetime
import warnings
import hashlib
from google.cloud import texttospeech
import subprocess
import sys




warnings.filterwarnings("ignore")

class Logger(object):
    def __init__(self, filename="log.txt"):
        self.terminal = sys.stdout
        self.log = open(filename, "w")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        pass


@staticmethod
def count_calls(func):
    def wrapper(*args, **kwargs):
        wrapper.calls += 1
        result = func(*args, **kwargs)
        return result, wrapper.calls  # 返回结果和调用次数
    wrapper.calls = 0
    return wrapper

def playsound(file_path):
    command = [
        'ffplay',
        '-autoexit',  # 播放完自动退出
        '-nodisp',    # 不显示视频窗口
        file_path
    ]
    
    try:
    # 运行 ffplay 命令，并将 stdout 和 stderr 重定向到 DEVNULL 以隐藏输出
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error playing audio: {e}")

class wfd_reviewer:
    def __init__(self, input_folder = './input', output_folder = './output', mp3_folder = './wfd_mp3'):
        self.wfd_table = None
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.tts = texttospeech.TextToSpeechClient()
        self.mp3_folder = mp3_folder

    def calculate_md5(self, data):
        data = self.remove_punctuations(data)
        md5_hash = hashlib.md5(data.encode()).hexdigest()
        return md5_hash

    def fix_path(self, path):
        #修正路径为系统格式
        return os.path.normpath(path)

    def first_time_init(self, path):
        path = os.path.join(self.input_folder, path)
        data = pd.read_csv(path, sep = '|', encoding = 'utf8')
        data['wrong'] = 0
        data['reviewed'] = 0
        data['wrong_date'] = pd.Series([[] for _ in range(len(data))])
        data['wrong_record'] = pd.Series([[] for _ in range(len(data))])
        data['md5'] = data['English Content'].apply(self.calculate_md5)
        data['mp3_path'] = data['md5'].apply(lambda x: os.path.join(self.mp3_folder, x + '.mp3'))
        self.wfd_table = data

    def attach_new_csv(self, path):
        # 读取新的 CSV 文件
        new_data = pd.read_csv(os.path.join(self.input_folder, path))
        time = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        self.wfd_table.to_csv(os.path.join(self.input_folder, 'wfd_table' + time + '.csv'), index = False, encoding = 'gbk')
        # 找出 wfd_table 中 English Content 不在 new_data 中的行，并将这些行删除
        self.wfd_table = self.wfd_table[self.wfd_table['English Content'].isin(new_data['English Content'])]

        # 找出 new_data 中 English Content 不在 wfd_table 中的行
        new_rows = new_data[~new_data['English Content'].isin(self.wfd_table['English Content'])]

        # 初始化新行的列
        new_rows['wrong'] = 0
        new_rows['reviewed'] = 0
        new_rows['wrong_date'] = pd.Series([[] for _ in range(len(new_rows))])
        new_rows['wrong_record'] = pd.Series([[] for _ in range(len(new_rows))])
        new_rows['md5'] = new_rows['English Content'].apply(self.calculate_md5)
        new_rows['mp3_path'] = new_rows['md5'].apply(lambda x: os.path.join(self.mp3_folder, x + '.mp3'))

        # 将新行添加到 wfd_table 中
        self.wfd_table = pd.concat([self.wfd_table, new_rows], ignore_index=True)
            

    def generate_mp3(self):
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Studio-M",
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            speaking_rate=1.2
        )
        cnt = 0
        for i in range(len(self.wfd_table)):
            if not os.path.exists(self.wfd_table['mp3_path'][i]):
                path = self.wfd_table['mp3_path'][i]
                synthesis_input = texttospeech.SynthesisInput(text=self.wfd_table['English Content'][i])
                response = self.tts.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
                with open(path, "wb") as out:
                    out.write(response.audio_content)
                print(f'MP3 Generated for Content: ', self.wfd_table['English Content'][i])
                cnt +=1
        print(f'{cnt} MP3 Generated')

    def load_existed_data(self, input_path):
        self.wfd_table = pd.read_csv(os.path.join(self.input_folder, input_path))
        self.wfd_table['wrong_date'] = self.wfd_table['wrong_date'].apply(eval)
        self.wfd_table['wrong_record'] = self.wfd_table['wrong_record'].apply(eval)

    def review(self, output_path, prob_range = 'all'):
        if prob_range == 'all':
            for i in range(len(self.wfd_table)):
                print(f'WFD Question Number {i + 1}')
                content = self.wfd_table['English Content'][i]
                mp3_path = self.wfd_table['mp3_path'][i]
                check_res, call_cnt = self.checker(content, mp3_path)
                res, stud_input = check_res
                if res == 'exit':
                    self.save_result(output_path)
                    print(f'Reviewed {call_cnt} Questions')
                    return
                if res == True:
                    self.wfd_table['reviewed'][i] += 1
                else:
                    self.wfd_table['wrong_date'][i].append(datetime.now().strftime("%Y-%m-%d"))
                    self.wfd_table['wrong'][i] += 1
                    self.wfd_table['reviewed'][i] += 1
                    self.wfd_table['wrong_record'][i].append(stud_input)
        else:
            prob_range_start = prob_range[0] - 1
            prob_range_end = prob_range[1]
            for i in range(prob_range_start, prob_range_end):
                print(f'WFD Question Number {i + 1}')
                content = self.wfd_table['English Content'][i]
                mp3_path = self.wfd_table['mp3_path'][i]
                check_res, call_cnt = self.checker(content, mp3_path)
                res, stud_input = check_res
                if res == 'exit':
                    self.save_result(output_path)
                    print(f'Reviewed {call_cnt} Questions')
                    return
                if res == True:
                    self.wfd_table['reviewed'][i] += 1
                else:
                    self.wfd_table['wrong_date'][i].append(datetime.now().strftime("%Y-%m-%d"))
                    self.wfd_table['wrong'][i] += 1
                    self.wfd_table['reviewed'][i] += 1
                    self.wfd_table['wrong_record'][i].append(stud_input)
        self.save_result(output_path)
        print(f'Reviewed {call_cnt} Questions')
        
    @count_calls
    def checker(self, target, mp3_path):
        playsound(mp3_path)
        stud_input = input('Enter Sentence You heard: ')
        if stud_input == 'exit':
            return 'exit', stud_input
        while stud_input == 'repeat':
            playsound(mp3_path)
            stud_input = input('Enter Sentence You heard: ')
        stud_input_dict = self.sentence_to_dict(stud_input)
        target_dict = self.sentence_to_dict(target)
        res = all(k in stud_input_dict and stud_input_dict[k] >= v for k, v in target_dict.items())
        if res == False:
            print(stud_input) # print for log
            print('Wrong Answer, answer is: ', target)
        return res, stud_input
                

    def remove_punctuations(self, text):
        text = text.translate(str.maketrans('', '', string.punctuation))
        text = text.strip()
        return text
    
    def sentence_to_dict(self, text):
        text = self.remove_punctuations(text)
        text = text.lower()
        word_counts = {}
        for word in text.split():
            if word in word_counts:
                word_counts[word] += 1
            else:
                word_counts[word] = 1
        return word_counts
    
    def save_result(self, output_path):
        self.wfd_table.to_csv(os.path.join(self.output_folder, output_path), index = False, encoding = 'gbk')
        print('Result Saved to ', os.path.join(self.output_folder, output_path))


if __name__ == '__main__':
    start_time_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    sys.stdout = Logger("./wfd_logs/" + start_time_str + ".txt")

    reviewer = wfd_reviewer()
    reviewer.first_time_init('wfd_316.csv')
    # reviewer.generate_mp3()
    reviewer.review(prob_range=[5, 10], output_path='wfd_test.csv')