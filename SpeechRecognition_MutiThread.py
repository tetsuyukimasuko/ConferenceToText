
#参照:
#https://qiita.com/clock/items/cb0cfce139af747a3c9f
#https://qiita.com/lethe2211/items/7c9b1b82c7eda40dafa9
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

#以下、調整可能な変数

#発話区間認識の閾値
DETECT_VOLUME=-40.0 #[dB]

#スレッド終了処理
Thread_Stop=False

#テキスト化マルチスレッド処理の個数
divide_count=4

#エンコーディングの指定
def check_encoding(binary):
    detector=UniversalDetector()
    detector.feed(binary)
    detector.close()
    return detector.result['encoding']

#指定したCHANK分のnp.arrayの実行値をとってデシベルにして返す
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

#発話区間認識+録音+途中経過をshelveで保存
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
            #print(dB)

            '''
            #絶対値をとる
            transfer_data=list(map(lambda x:np.abs(x),tmp_data))
        
            #平均値計算
            avg=np.average(transfer_data)
            '''

            #平均値が閾値以上であれば、Stream_writeをTrueにする。かつ、無音カウンターを0にする。
            #閾値以下で、かつStream_writeが既にTrueだったら、カウンターを1つ足す。
            #カウンターが10つたまったら、Stream_endをTrueにする
            if dB>DETECT_VOLUME:
                Stream_write=True
                silent_sounter=0
            else:
                if Stream_write:
                    silent_sounter+=1
                    if silent_sounter>10:
                        Stream_end=True

            #stream_writeがfalseなら、バッファに追加。
            #もしバッファが7つになっちゃったら先頭を削除する。
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
        shelf_file=shelve.open(user_name)
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

#Googleに繋いでテキスト化
#.jsonはサービスアカウントのものを使用
def SpeechToText(spoken_time,audio_data,total,filename,speaker):
    i=0
    k=0
    with open(r"XXXXX.json", "r") as f:
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

#リストを特定の数で分割して返す
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

#csvをマージして、dataframeにした後、時間で並び替えて、CSV吐き出し。
def MergeCSV(filelist,output):
    list = []

    for f in filelist:
        list.append(pd.read_csv(f,encoding='shift-jis'))
    df = pd.concat(list)
    df=df.sort_values(by=["time"], ascending=True)
    df.to_csv(output,index=False)

#ShelveをCSVに変換
def ShelveToCSV(filename,csvfilename):
    global divide_count
    shelf_file=shelve.open(filename)
    audio_data=list(shelf_file['audio_data'])
    spoken_time=list(shelf_file['spoken_time'])
    shelf_file.close()
    r = sr.Recognizer()
    fp=open(csvfilename,'w')
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
        title='subrutin'+str(i)+'.csv'
        file_list.append(title)

    threads=[]
    for i in range(divide_count):
        thread=threading.Thread(target=SpeechToText,args=(time_list[i],audio_list[i],total,file_list[i],filename))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    #マージ処理
    MergeCSV(file_list,csvfilename)
    string='Converting '+filename+space+'|====================| CSV Saved.\n'
    sys.stdout.write('\r' + string)
    sys.stdout.flush()
    fp.close()
    
#めいん    
if __name__ == '__main__':
    
    names=[]
    mics=[]

    pa = pyaudio.PyAudio()
    print('Sound Devices : ')
    for device_index in range(pa.get_device_count()):
        metadata = pa.get_device_info_by_index(device_index)
        try:
            encoding=check_encoding(metadata['name'])
            print(device_index, metadata["name"].decode(encoding))
        except:
            print(device_index, metadata["name"].replace('ƒ}ƒCƒN','マイク'))
    print('------------------------------')


    print('Input numbers of participants---',end='')
    num=int(input())
    print()
    for i in range(num):

        print("What's your name?---",end='')
        names.append(input())

        print("Select mic index---",end='')
        mics.append(int(input()))

    print('------------------------------')

    print('Speak!')
    print('To stop program---Ctrl+C')

    try:
        #簡易発話区間認識+録音。ここをマルチスレッド化。
        threads=[]
        for i in range(num):
            thread=threading.Thread(target=VoiceDetection,args=(mics[i],names[i]))
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
        for name in names:
            ShelveToCSV(name,name+'.csv')
        #マージ処理
        for i in range(len(names)):
            names[i]=names[i]+'.csv'
        MergeCSV(names,'result.csv')
        print()
        print('Completed!')

    finally:
        print('Press Enter to exit---')
        input()
        sys.exit(0)
