"""Export live MCP schemas and read-only encyclopedia examples (no map generation)."""
import argparse
import json
from pathlib import Path
import sys

import anyio
from mcp import Client, StdioServerParameters


async def export(workspace,output):
    params=StdioServerParameters(command=sys.executable,
        args=['-m','h3m.mcp_server','--workspace',str(workspace)],env={'PYTHONUTF8':'1'})
    with anyio.fail_after(60):
        async with Client(params) as client:
            tools=await client.list_tools()
            output.mkdir(parents=True,exist_ok=True)
            (output/'mcp-tools.schema.json').write_text(json.dumps(tools.model_dump(mode='json',by_alias=True,exclude_none=True),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            examples=[]
            for name,args in [('catalog_search',{'category':'artifacts','query':'защита от ослепления'}),
                              ('catalog_get',{'category':'artifacts','id':11}),
                              ('catalog_get',{'category':'creatures','id':97}),
                              ('catalog_get',{'category':'spells','id':38}),
                              ('catalog_get',{'category':'creatures','id':153}),
                              ('catalog_search',{'category':'creatures','faction':'bulwark'}),
                              ('catalog_get',{'category':'creatures','id':197,'ruleset':'hota_1.8.0'}),
                              ('catalog_get',{'category':'creatures','id':197,'ruleset':'hota_1.8.1'}),
                              ('catalog_search',{'category':'creatures','faction':'Некрополис'}),
                              ('catalog_get',{'category':'creatures','id':130}),
                              ('catalog_get',{'category':'creatures','id':8}),
                              ('catalog_search',{'category':'artifacts','tag':'сборный'}),
                              ('catalog_get',{'category':'artifacts','id':129}),
                              ('catalog_get',{'category':'artifacts','id':160}),
                              ('catalog_get',{'category':'artifacts','id':158}),
                              ('catalog_get',{'category':'creatures','id':65000})]:
                result=await client.call_tool(name,args)
                if result.is_error:raise RuntimeError(str(result))
                examples.append(dict(tool=name,arguments=args,result=result.structured_content))
            (output/'mcp-catalog.examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(f'{len(tools.tools)} tools; schemas and {len(examples)} examples saved in {output}')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--output',type=Path)
    a=p.parse_args();root=a.workspace.resolve()
    anyio.run(export,root,a.output.resolve() if a.output else root/'out')


if __name__=='__main__':main()
