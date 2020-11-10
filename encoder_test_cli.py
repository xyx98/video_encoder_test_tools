import os,sys
import argparse

from encoder_test_tools import tester

if __name__ == "__main__":
    class args:
        pass

    parser = argparse.ArgumentParser(description='A simple command line interface for encoder_test_tools with limited function\nOnly vapoursynth scripts with absolute path in source filter are supported currently\nvspipe and encoder you chosen need in your environment variables',formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-src","--src",required=True,type=str,help="Source,must be a vapoursynth script")
    parser.add_argument("-e","--encoder",required=True,type=str,help="Select which encoder you want use.\nCurrently,only x264、x265、vpx and svt-av1 can work.Do not add suffix,for svt-av1,you should use SvtAv1EncApp")
    parser.add_argument("-q","--quality",required=True,type=str,help="A number list split by comma,use for setting different qps or crfs,base on your base_args")
    parser.add_argument("-b","--base_args",required=True,type=str,help="""set your encoder args your test based on,refer to this example(svt-av1):\n"-i stdin --input-depth 10 --rc 0 --irefresh-type 2 --keyint 299 --lp 8  -q {q} --{test} -b \\"{o}\\"" \nUse '\\"' instead of '"'.""")
    parser.add_argument("-t","--test_arg",required=True,type=str,help="set which args you want test")
    parser.add_argument("-v","--value",required=True,type=str,help="set values for arg you want test,use comma split each value")
    parser.add_argument("-l","--link",type=str,default=" ",help="set linker between test arg and value.By default,use blank space")
    parser.add_argument("-s","--suffix",type=str,default="",help='set suffix for video encoder output.Usually,it affect nothing,but we still suggest setting a normal value.Do not forget "." .')
    parser.parse_args(sys.argv[1:],args)

    src=args.src
    encoder=args.encoder
    q=args.quality.split(",")
    base_args=args.base_args
    test_arg=args.test_arg
    value=args.value.split(",")
    link=args.link
    suffix=args.suffix

    #print(base_args)
    test=tester(src,encoder,base_args,test_arg,value,q,link,test_arg,suffix)
    test.run()
    test.report()
