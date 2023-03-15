#python
import os,sys
import subprocess
import re
import textwrap
import pathlib
import shutil
import csv
import statistics

from pyecharts.charts import Line
import pyecharts.options as opts
from pyecharts.globals import ThemeType
from pyecharts.commons import utils as pyecharts_utils

from bs4 import BeautifulSoup

class utils:
    @staticmethod
    def applybackspace(s):
        tmp=[]
        for i in s:
            if i!="\b":
                tmp.append(i)
            elif len(tmp)>0:
                tmp.pop()
        return "".join(tmp)

    @staticmethod
    def calc_score(path:str,mode:str="harmonic"):
        if mode not in ["harmonic","mean","quadratic","geometric"]:
            raise ValueError("unknown mode")

        if mode=="harmonic":
            mean=statistics.harmonic_mean
        elif mode=="mean":
            mean=statistics.fmean
        elif mode=="geometric":
            mean=statistics.geometric_mean
        else:
            mean=lambda i: (sum(map(lambda x: x**2),i)/len(i))**0.5
        
        ssim,ms_ssim,vmaf=[],[],[]
        with open(path) as file:
            data=csv.DictReader(file)
            for line in data:
                ssim.append(float(line["float_ssim"]))
                #ms_ssim.append(float(line["ms_ssim"]))
                vmaf.append(float(line["vmaf"]))

        return mean(ssim),'No Data',mean(vmaf) #mean(ssim),mean(ms_ssim),mean(vmaf)

    @staticmethod
    def cls():
        if os.name=="nt":
            os.system("cls")
        else:
            os.system("clear")

class process_log:
    def __init__(self,method=None):
        if method is None:
            method=self.svtav1
        self.process=method

    def run(self,path):
        return self.process(path)

    @staticmethod
    def svtav1(path:str):
        with open(path,"r") as file:
            log=file.read()
        matchfps=re.search(r"Average Speed.+?([0-9.]+) fps",log)
        matchbits=re.search(r".+?([0-9.]+) kbps",log)

        fps=float(matchfps.group(1)) if matchfps else None
        bitrate=float(matchbits.group(1)) if matchbits else None

        return fps,bitrate

    @staticmethod
    def x265(path:str):
        with open(path,"r") as file:
            log=file.read()

        match=re.search(r"encoded.+\(([0-9.]+) fps\), ([0-9.]+) kb/s",log)

        fps=None
        bitrate=None
        if match:
            fps=float(match.group(1))
            bitrate=float(match.group(2))

        return fps,bitrate

    @staticmethod
    def x264(path:str):
        with open(path,"r") as file:
            log=file.read()

        match=re.search(r"encoded.+ ([0-9.]+) fps, ([0-9.]+) kb/s",log)

        fps=None
        bitrate=None
        if match:
            fps=float(match.group(1))
            bitrate=float(match.group(2))

        return fps,bitrate

    @staticmethod
    def vpx(path:str):
        with open(path,"r") as file:
            log=file.read()

        match=re.search(r".+ ([0-9.]+)b/s.+\(([0-9.]+) fps\)",log)

        fps=None
        bitrate=None
        if match:
            fps=float(match.group(2))
            bitrate=float(match.group(1))/1024

        return fps,bitrate

    @staticmethod
    def ffmpeg(path:str):
        with open(path,"r") as file:
            log=[i for i in file if i.startswith("frame=")][-1]

        match=re.search(r"fps= *([0-9.]+).+bitrate= *([0-9.]+)kbits/s",log)

        fps=None
        bitrate=None
        if match:
            fps=float(match.group(1))
            bitrate=float(match.group(2))

        return fps,bitrate
    
class encode:
    def __init__(self,cmd:str,i:str,o:str,suffix:str,i_charset:str,twopass):
        self.cmd=cmd
        self.input=i
        self.output=o
        self.suffix=suffix
        self.charset=i_charset
        self.twopass=twopass

    def encoder(self):
        cmd=self.cmd.format(i=self.input,o=self.output+self.suffix,passopt="{passopt}")
        if self.twopass:
            cmd1=cmd.format(passopt=f'--pass 1 --stats "{self.output}_2pass.log"')
            cmd=cmd.format(passopt=f'--pass 2 --stats "{self.output}_2pass.log"')
            print(cmd1)
            firstpass=subprocess.run(cmd1,shell=True)
            if firstpass.returncode:
                raise BrokenPipeError
        else:
            cmd=cmd.format(passopt='')
        print(cmd)
        sp=subprocess.Popen(cmd,shell=True,stderr=subprocess.PIPE,stdout=subprocess.PIPE)
        logtext=""
        while(True):
            stats=sp.poll()
            if stats is not None:
                info=sp.stderr.read()
                if isinstance(info,bytes):
                    info=info.decode("utf-8")
                logtext+=info
                sys.stderr.write(info)
                sys.stderr.flush()

                with open(f"{self.output}.log","w") as file:
                    file.write(utils.applybackspace(logtext))
                return stats==0
            else:
                info=sp.stderr.read(1)
                if isinstance(info,bytes):
                    info=info.decode("utf-8")
                logtext+=info
                sys.stderr.write(info)
                sys.stderr.flush()
        
    def vmaf(self):
        rex=re.compile(r"(.+)\.set_output\(\)")

        with open(self.input,"r",encoding=self.charset) as file:
            script=file.read()

        match=rex.search(script)
        clip=match.group(1)
        script=rex.sub("",script)
        script+=f'rip=core.lsmas.LWLibavSource(r"{self.output}_fin{self.suffix}")\n'
        script+=f'rip=core.resize.Spline36(rip,{clip}.width,{clip}.height,format={clip}.format)\n'
        script+=f'last=core.vmaf.VMAF({clip},rip, model=0,log_path="{self.output}.csv", log_format=2, feature=2)\n'
        script+=f'last.set_output()'

        with open("vmaf.vpy","w",encoding=self.charset) as file:
            file.write(script)
        
        sp=subprocess.run(f'vspipe -p "vmaf.vpy" .',shell=True)
        return sp.returncode==0
        
    def run(self):
        if os.path.exists(f"{self.output}_fin.csv"):
            return True
        
        if not os.path.exists(f"{self.output}_fin{self.suffix}"):
            if os.path.exists(f"{self.output}{self.suffix}"):
                os.remove(f"{self.output}{self.suffix}")
            enc=self.encoder()
            if not enc:
                return False
            else:
                os.rename(f"{self.output}{self.suffix}",f"{self.output}_fin{self.suffix}")
            
        if os.path.exists(f"{self.output}.csv"):
            os.remove(f"{self.output}.csv")
        
        vmaf=self.vmaf()
        if not vmaf:
            return False
        else:
            os.rename(f"{self.output}.csv",f"{self.output}_fin.csv")
        
        return True

class single_tester:
    def __init__(self,i:str,name:str,suffix:str,q:list,cmd:str,i_charset:str,process_log_method,twopass):
        self.input=i
        self.qlist=q
        self.cmd=cmd
        self.name=name
        self.suffix=suffix
        self.charset=i_charset
        self.log=process_log_method
        self.data=[]
        self.fail_log=[]
        self.twopass=twopass

    def run(self):
        mark=True
        for q in self.qlist:
            utils.cls()
            enc=encode(cmd=self.cmd.format(q=q,i="{i}",o="{o}",passopt="{passopt}"),i=self.input,o=f"{self.name}.q{q}",suffix=self.suffix,i_charset=self.charset,twopass=self.twopass)
            run=enc.run()
            mark=mark and run
            if run:
                template={"q":q}
                fps,bitrate=self.log(f"{self.name}.q{q}.log")
                if fps is None or bitrate is None:
                    self.fail_log.append(f"fails in q{q}:consider rewrite process_log_method to process log")
                    mark=False
                template["bitrate"]=bitrate
                template["speed"]=fps
                template["ssim"],template["ms_ssim"],template["vmaf"]=utils.calc_score(f"{self.name}.q{q}_fin.csv")
                self.data.append(template)
        return mark

    def getdata(self):
        return self.data
    
    def datatofile(self,path:str = None):
        if path is None:
            path=f"{self.name}.data"
        with open(path,"w") as file:
            file.write("q\tbitrate\tspeed\tssim\tms_ssim\tvmaf")
        
            for line in self.data:
                file.write(f'\n{line["q"]}\t{line["speed"]}\t{line["ssim"]}\t{line["ms_ssim"]}\t{line["vmaf"]}')

class chart:
    def __init__(self,title:str,output:str):
        self.title=title
        self.output=output
        self.datas=[]
        self.chart=(
            Line(init_opts=opts.InitOpts(
                    page_title=self.title,
                    theme=ThemeType.DARK,
                    width="1280px",
                    height="720px",
                    )
                )
            .set_global_opts(
                title_opts=opts.TitleOpts(title=self.title),
                xaxis_opts=opts.AxisOpts(type_="value",is_scale=True,split_number=10,name="bitrate/kbps"),
                yaxis_opts=opts.AxisOpts(type_="value",is_scale=True,name="vmaf"),
                toolbox_opts=opts.ToolboxOpts(
                    is_show=True,
                    orient="vertical",
                    pos_left="right",
                    feature=opts.ToolBoxFeatureOpts(
                        save_as_image=opts.ToolBoxFeatureSaveAsImageOpts(title="save as image",is_show=True),
                        restore=opts.ToolBoxFeatureRestoreOpts(is_show=False),
                        data_zoom=opts.ToolBoxFeatureDataZoomOpts(is_show=False),
                        data_view=opts.ToolBoxFeatureDataViewOpts(is_show=False,is_read_only=True,title="data"),
                        magic_type=opts.ToolBoxFeatureMagicTypeOpts(is_show=False),
                        brush=opts.ToolBoxFeatureBrushOpts(type_=[])
                        )
                    ),
                legend_opts=opts.LegendOpts(pos_top="bottom"),
                tooltip_opts=opts.TooltipOpts(
                    is_show=True,
                    formatter=pyecharts_utils.JsCode("function(x) {return x.seriesName + '<br/>bitrate&nbsp;&nbsp;'+ x.data[0] + '&nbsp;kbps<br/>vmaf&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;' + x.data[1];}")
                )
            )
        )
        
    def render(self):
        all_bitrate=sum([[t[0] for t in i["data"]] for i in self.datas],[])
        maxb=max(all_bitrate)
        minb=min(all_bitrate)
        delta=maxb-minb
        upper=round(maxb+delta*0.05)
        lower=round(minb-delta*0.05)

        x_data=list(range(lower,upper+1))
        self.chart.add_xaxis(x_data)

        for i in self.datas:
            y_data=[None]*len(x_data)
            for b,v in i["data"]:
                y_data[round(b)-lower]=v
            
            self.chart.add_yaxis(i["name"], y_data, is_connect_nones=True,is_smooth=True,
                label_opts=opts.LabelOpts(is_show=False),
                linestyle_opts=opts.LineStyleOpts(width=1,curve=10),
                symbol_size=10
            )

        self.chart.render(self.output)

    def add(self,data:list,name:str):
        self.datas.append({"name":name,"data":[(i["bitrate"],i["vmaf"]) for i in data]})

    def addfromfile(self,path,name):
        with open(path,"r") as file:
            data=list(csv.DictReader(file,delimiter="\t"))
        
        self.add(data,name)

class htmlreport:
    def __init__(self,html:str):
        self.soup=BeautifulSoup(html,"html.parser")
        css="""<style>
                body{
                    background-color:rgb(51, 51, 51);
                    color: khaki;
                }

                td{
                    padding-right: 2em;
                }
                th{
                    text-align: left;
                    padding-right: 2em;
                }
                .extra{
                    width: 30%;
                }
                </style>"""
        self.soup.head.append(BeautifulSoup(css,"html.parser"))

    def addtable(self,title:str,data:list,head:list = None,extra:str = None,process=None):
        if process is None:
            process=lambda x,y: str(x[y])
        if head is None:
            head=list(data[0].keys())
        self.soup.body.append(BeautifulSoup(f"</br><h3>{title}</h3>","html.parser"))
        table="<table><tbody><tr><th>"+"</th><th>".join(head)+"</th>{extra}</tr>"+"{lines}</tbody></table>"
        lines=""
        for i in data:
            lines+=("<tr><td>"+"</td><td>".join([process(i,t) for t in head])+"</td><td>")
        if extra is None:
            extra=""
        else:
            extra=f'<td rowspan={len(data)+1} class="extra">{extra}</td>'
        table=table.format(extra=extra,lines=lines)
        self.soup.body.append(BeautifulSoup(table,"html.parser"))

    def save(self,path:str):
        with open(path,"w",encoding="utf-8") as file:
            file.write(self.soup.prettify())

class tester:
    def __init__(self,src:str,encoder:str,base_args:str,test_arg:str,value=None,quality=[24,27,30,33,36],link:str=" ",workspace:str="",suffix="",process_log_method=None,i_charset="utf-8",twopass=False):
        self.source=src
        self.charset=i_charset
        self.argsbooltype=not isinstance(value,list)
        self.fail=[]
        self.result=[]
        self.quality=quality
        if not workspace:
            workspace=test_arg
        
        self.workspace=pathlib.Path(workspace)
        self.testlist=["",test_arg] if self.argsbooltype else [f"{test_arg}{link}{i}" for i in value]
        self.encoder=encoder
        self.base_args=base_args
        self.suffix=suffix
        self.chart=chart(title=self.encoder,output="report.html")
        self.cmd='vspipe -c y4m "{i}" -|'+self.encoder+" "+self.base_args
        self.twopass=twopass

        if process_log_method is None:
            if encoder=="x264":
                self.process_log=process_log.x264
            elif encoder=="x265":
                self.process_log=process_log.x265
            elif encoder=="vpxenc":
                self.process_log=process_log.vpx
            elif encoder.lower()=="svtav1encapp" or encoder=="sav1":
                self.process_log=process_log.svtav1
            else:
                self.process_log=process_log.ffmpeg

    def init_workspace(self,clean=False):
        if self.workspace.is_dir():
            if clean:
                shutil.rmtree(str(self.workspace))
                os.mkdir(self.workspace)
            shutil.copy(self.source,str(self.workspace))
        else:
            os.mkdir(self.workspace)
            shutil.copy(self.source,str(self.workspace))
        os.chdir(self.workspace)

    def run(self):
        self.init_workspace()
        for test in self.testlist:
            utils.cls()
            cmd=self.cmd.format(test=test,q="{q}",i="{i}",o="{o}",passopt="{passopt}")
            st=single_tester(i=self.source,name=''.join(i if i not in r'\/:*?"<>|' else '_' for i in test),suffix=self.suffix,q=self.quality,cmd=cmd,i_charset=self.charset,process_log_method=self.process_log,twopass=self.twopass)
            run=st.run()
            if not run:
                self.fail.append(test)
                continue
            self.result.append({"test":test,"data":st.getdata()})
        utils.cls()

    def report(self,):
        for r in self.result:
            self.chart.add(r["data"],r["test"])
        self.chart.render()
        with open("report.html","r") as file:
            html=file.read()
        
        report=htmlreport(html)
        for r in self.result:
            report.addtable(r["test"],r["data"],["q","bitrate","ssim","ms_ssim","vmaf","speed"],
                process=lambda x,y: str(x[y])+"&ensp;fps" if y=="speed" else str(x[y])+"&ensp;kbps" if y=="bitrate" else str(x[y]),
                extra=self.encoder+" "+self.base_args.format(test=r["test"],q="{q}",o="{o}",passopt="<2-PASS_OPTS>" if self.twopass else ''))
        report.save("report.html")

if __name__ == "__main__":
    src=r"Untitled.vpy"
    encoder=r"x264"
    base_args=r'--demuxer y4m --bitrate {q} --{test} {passopt} -o "{o}" -'
    test_arg="preset"
    value=[1,2]
    
    test=tester(src,encoder,base_args,test_arg,value,suffix=".h264",quality=[2000,3000,5000],workspace='',link=' ',twopass=True)
    test.run()
    test.report()
    input('\npress enter to exit')


        
