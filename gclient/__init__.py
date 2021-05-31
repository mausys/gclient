import sys,os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ['DEPOT_TOOLS_COLLECT_METRICS'] = "0"
os.environ['DEPOT_TOOLS_REPORT_BUILD'] =  "0"
