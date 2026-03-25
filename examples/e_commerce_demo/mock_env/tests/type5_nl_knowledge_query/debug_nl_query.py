from datacloud_knowledge import reset_singleton_service
from pathlib import Path
from dotenv import load_dotenv

from datacloud_knowledge import SQLKnowledgeGraphQuery, TreeNode, nl_to_semantic_tree

def main():

    env_path = Path(__file__).resolve().parents[2] / ".env.example"
    if env_path.exists():
        load_dotenv(env_path, override=True)

    query = '帮我看一下"北京亦庄经济技术开发区"区域内单位亩产效益最低的10家企业'
    
    text = nl_to_semantic_tree(query, n_hops=2)
    print(text)

    reset_singleton_service()

if __name__ == '__main__':
    main()