
#google speech apiでやるぞお！
#コードはhttps://qiita.com/clock/items/cb0cfce139af747a3c9fを参照
#API利用に関してはhttps://qiita.com/lethe2211/items/7c9b1b82c7eda40dafa9を参照
#https://qiita.com/sayonari/items/a70118a468483967ad34
#https://cloud.google.com/speech/docs/streaming-recognize?hl=ja#speech-streaming-recognize-csharp

#サードパーティ
import speech_recognition as sr
import pyaudio
from chardet import UniversalDetector

#Anaconda標準
import shelve
import wave
import time
import math
import numpy as np
import sys
import threading
import pandas as pd
import os
import shutil

#以下、調整可能な変数

#発話区間認識の閾値
#これはマイク性能でかなり変わる。事前に調整が必要。
DETECT_VOLUME=-60.0 #[dB]

#スレッド終了処理
Thread_Stop=False

#テキスト化マルチスレッド処理の個数
divide_count=4

def check_encoding(binary):
    detector=UniversalDetector()
    detector.feed(binary)
    detector.close()
    return detector.result['encoding']

#指定したCHUNK分のnp.arrayの実行値をとってデシベルにして返す
#https://oshiete.goo.ne.jp/qa/5103185.html
#https://detail.chiebukuro.yahoo.co.jp/qa/question_detail/q1050536775
def ConvertToDB(array):
    n=len(array)
    
    #二乗和
    tmp=np.square(array)
    sm=np.sum(tmp)

    #実効値
    V=sm/n

    #デシベル
    dB=20*math.log10(V)

    return dB

def VoiceDetection(device,user_name):
    CHUNK = 2048
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    global DETECT_VOLUME
    global Thread_Stop


    while True:
        #pyaudio開始
        frames = []
        bufferframes=[]
        Stream_write=False
        Stream_end=False
        silent_sounter=0
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT,
                channels=CHANNELS,
                input_device_index=device,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK)


        #発話区間認識。何かしゃべったら抜け出す
        while True:
 
            data = stream.read(CHUNK)

            #各フレームの振幅をとる。-0.1～0.1で正規化。
            tmp_data=np.frombuffer(data, dtype="int16")/32768.0
            
            #デシベル変換
            dB=ConvertToDB(tmp_data)

            #sys.stdout.write("\r%f"% dB)
            #sys.stdout.flush()

            #平均値が閾値以上であれば、Stream_writeをTrueにする。かつ、無音カウンターを0にする。
            #閾値以下で、かつStream_writeが既にTrueだったら、カウンターを1つ足す。
            #カウンターが7つ(0.9秒)たまったら、Stream_endをTrueにする
            #ただし、発話途中で一時的に音量が下がっているだけだったら、無音カウンターは0に戻す。
            #このときの閾値はDETECT_VOLUME-10[dB]とする。

            if dB>DETECT_VOLUME:
                Stream_write=True
                silent_sounter=0
            else:
                if Stream_write:
                    if dB>DETECT_VOLUME-10:
                        silent_sounter=0
                    else:
                        silent_sounter+=1

                    if silent_sounter>7:
                        Stream_end=True

            #stream_writeがfalseなら、バッファに追加。
            #もしバッファが7つ(0.9秒)になっちゃったら先頭を削除する。
            #もしtrueなら、framesに追加
            if not Stream_write:
                bufferframes.append(data)
                if len(bufferframes)>7:
                    del bufferframes[0]
            else:
                frames.append(data)

            if Stream_end:
                frames=bufferframes+frames
                break

            if Thread_Stop:
                break

        if Thread_Stop:
            break
        
        print("* done recording")
        stream.stop_stream()
        stream.close()
        p.terminate()
        tmp=b''.join(frames)
        audio=sr.AudioData(tmp,RATE,2)
    
        #保存用shelfをつくる
        shelf_file=shelve.open(user_name+"/"+user_name)
        try:
            tmp=list(shelf_file['audio_data'])
            tmp.append(audio)
            shelf_file['audio_data']=tmp
        except:
            shelf_file['audio_data']=[audio]
        try:
            tmp=list(shelf_file['spoken_time'])
            tmp.append(str(time.ctime()))
            shelf_file['spoken_time']=tmp
        except:
            shelf_file['spoken_time']=[str(time.ctime())]

        shelf_file.close()

def SpeechToText(spoken_time,audio_data,total,filename,speaker):
    i=0
    k=0
    with open(r"My First Project-63da92b78953.json", "r") as f:
        credentials_json = f.read()
    r=sr.Recognizer()
    fp=open(filename,'w')
    fp.write("time,text,speaker\n")
    for (t,audio) in zip(spoken_time,audio_data):
        i+=1.0
        try:
            num=i/total*100
            if num/5>1.0:
                tmp=np.round(int(num/5.0))
                for j in range(tmp-k):
                    sys.stdout.write("=")
                    k=k+1
                    sys.stdout.flush()            
            txt=r.recognize_google_cloud(audio,language='ja',credentials_json=credentials_json)
            fp.write(t+','+txt+','+speaker+'\n')

        except:
            pass

    sys.stdout.flush()
    fp.close()

def list_no_list(lst,num):
    count=len(lst)
    list_no_list1=[]
    divided=int(np.round(count/num))+1

    for j in range(num):
        #1つあたりの数を求めたい。
        start=j*divided
        end=start+divided-1
        if end>count-1:
            end=count-1

        tmp=lst[start:end+1]
        list_no_list1.append(tmp)

    return list_no_list1

def MergeCSV(filelist,output):
    #csvをマージして、dataframeにした後、時間で並び替えて、CSV吐き出し。
    list = []

    for f in filelist:
        list.append(pd.read_csv(f,encoding='shift-jis'))
    df = pd.concat(list)
    df=df.sort_values(by=["time"], ascending=True)
    df.to_csv(output,index=False)

def ShelveToCSV(filename,csvfilename):
    global divide_count
    cwd=filename+"/"
    shelf_file=shelve.open(cwd+filename)
    audio_data=list(shelf_file['audio_data'])
    spoken_time=list(shelf_file['spoken_time'])
    shelf_file.close()
    r = sr.Recognizer()
    fp=open(cwd+csvfilename,'w')
    total=len(audio_data)
    i=0
    k=0
    tmp=0
    space=""
    
    if len(filename)<15:
        spacing=15-len(filename)
    else:
        filename=filename[0:15]
        spacing=0

    for x in range(spacing):
        space=space+" "
    string='Converting '+filename+space+'|'
    sys.stdout.write(string)

    #ここをマルチスレッドにする！
    #リストのリストを返す関数

    audio_list=list_no_list(audio_data,divide_count)
    time_list=list_no_list(spoken_time,divide_count)
    file_list=[]
    for i in range(divide_count):
        title=cwd+'subrutin'+str(i)+'.csv'
        file_list.append(title)

    threads=[]
    for i in range(divide_count):
        thread=threading.Thread(target=SpeechToText,args=(time_list[i],audio_list[i],total,file_list[i],filename))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    #マージ処理
    MergeCSV(file_list,cwd+csvfilename)
    string='Converting '+filename+space+'|====================| CSV Saved.\n'
    sys.stdout.write('\r' + string)
    sys.stdout.flush()
    fp.close()

Detect_Finish=False
user_names=[]
mics_used=[]

#マイク入力音量が一定値を超えたらDetect_Mic_UserをFalseにして、Detected_Deviceにマイク番号を入れる関数
#ストリームpを引数にとる
def Detect_Mic(p,device_num,stream):
    
    global Detect_Finish
    global mics_used
    detect_counter=0
    CHUNK = 2048

    while True:
 
        data = stream.read(CHUNK)

        #各フレームの振幅をとる。-0.1～0.1で正規化。
        tmp_data=np.frombuffer(data, dtype="int16")/32768.0
            
        #デシベル変換
        dB=ConvertToDB(tmp_data)
        sys.stdout.write("\r%f"% dB)
        sys.stdout.flush()
        #平均値が閾値以上であれば、有音カウンターを1つ足す。
        #カウンターが10つたまったら、Detect_FinishをTrueにする

        if dB>DETECT_VOLUME:
            detect_counter+=1
        else:
            detect_counter=0
        
        if detect_counter>10:
            Detect_Finish=True
            mics_used.append(device_num)
            print('Your mic No. :',device_num)
            break

        if Detect_Finish:
            break

#上記関数をマルチで動かして、マイク割り当てをする関数
#会議参加者numを引数に、namesとmicsを返す
def Catch_Mic_User(num):

    global Detect_Finish
    global user_names

    CHUNK = 2048
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    #デバイス表示
    mic_index_list=[]
    pa = pyaudio.PyAudio()
    print('Sound Devices : ')
    for device_index in range(pa.get_device_count()):
        metadata = pa.get_device_info_by_index(device_index)
        try:
            encoding=check_encoding(metadata['name'])
        except:
            #ここの条件は変えよう
            if 'Realtek' not in metadata['name']:
                mic_index_list.append(device_index)
                print(device_index, metadata["name"].replace('ƒ}ƒCƒN','マイク'))

    pa.terminate()

    if num>len(mic_index_list):
        print()
        print('********************************************************')
        print('!!Caution!! The number of mic is less than participants.')
        print('********************************************************')
        input()
        sys.exit(0)

    for i in range(num):
        Detect_Finish=False
        print('No.',i+1)
        print("What's your name?---",end='')
        user_names.append(input())

        print('Speak to your mic (min. 2[s])')
        threads=[]

        for j in range(len(mic_index_list)):
            #重複はさせない
            if not mic_index_list[j] in mics_used:
                p = pyaudio.PyAudio()
                stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        input_device_index=mic_index_list[j],
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)
                thread=threading.Thread(target=Detect_Mic,args=(p,mic_index_list[j],stream))
                threads.append(thread)
                thread.start()

        for thread in threads:
            thread.join()
       
if __name__ == '__main__':
    

    print('Input numbers of participants---',end='')
    num=int(input())
    print()

    #追加あああああああああああああああああああああああああああああ
    Catch_Mic_User(num)
    print(user_names,mics_used)
    #あああああああああああああああああああああああああああ



    for i in range(num):

        if not os.path.exists(user_names[i]):
            os.makedirs(user_names[i])
        else:
            #前回の内容を削除するかどうか聞く。
            print('Data of',user_names[i],'already exists. Allow overwrite? [y/n]---',end='')
            res=input()
            if res=="y":
                shutil.rmtree(user_names[i])
                os.makedirs(user_names[i])

    print('------------------------------')

    print('Speak!')
    print('To stop program---Ctrl+C')

    try:
        #簡易発話区間認識+録音。ここをマルチスレッド化。
        threads=[]
        for i in range(num):
            thread=threading.Thread(target=VoiceDetection,args=(mics_used[i],user_names[i]))
            threads.append(thread)
            thread.start()

        #join() メソッドを呼ぶときに、タイムアウトを設定して、ループする。こうすると、KeyboardInterruptを受け取れる。
        #http://methane.hatenablog.jp/entry/20110518/1305715919
        for thread in threads:
            while True:
                thread.join(0.5)

    except KeyboardInterrupt:
        Thread_Stop=True
        print('------------------------------')
        print('Finish sequence. Start converting text.')
        print()
        print('Progress :              0%|                    |100%')
        for name in user_names:
            ShelveToCSV(name,name+'.csv')
        #マージ処理
        for i in range(len(user_names)):
            user_names[i]=user_names[i]+"/"+user_names[i]+'.csv'
        MergeCSV(user_names,'result.csv')
        print()
        print('Completed!')

    finally:
        print('Press Enter to exit---')
        input()
        sys.exit(0)
