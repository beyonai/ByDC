# ֪ʶ��ǿ Pipeline ��ƣ�2026-04-01��

## 1. ����
- ���� knowledge_enhance_node ֻ���û�����ֱ��ι�� search_knowledge���޷��õ� LLM ����������Ｏ�ϣ�Ҳ�޷����� confirmed / ambiguous �Ƚṹ����Ϣ��
- ��ģ�����/֪ʶ��ǿ���ĵ���ȷҪ��һ�β��� 5.1~5.5 ���ܣ������ȡ����ѡ���������崦����֪ʶ���ء��������ɡ�
- �Ͻڵ���� 	erm_hints/enriched_query/knowledge_snippets/knowledge_preview������ preview �������������ߣ���Ҫ�Ƴ���

## 2. ���Ŀ��
1. ��֪ʶ��ǿ���̸���ɹ̶� 5 ���� pipeline�����ε��ü����õ����нṹ�������
2. AgentState ���� concept_terms/confirmed_terms/ambiguous_terms/knowledge_payload ���ع� 	erm_hints/enriched_query/knowledge_snippets �����ɷ�ʽ��
3. ��һ��ʧ�ܶ��ܽ����ؾ� search_knowledge ���̣������ж���ͼ��
4. ���߼�Ĭ���� pipeline��fallback ֻ���쳣ʱ��������־Ҫ�ܸ���ÿһ���ؼ�ָ�꣬�����Ų顣

## 3. �ܹ�����
- �� knowledge_enhance/node.py ���� KnowledgeEnhancePipeline �࣬��¶ sync run(context) -> PipelineOutput��
- LangGraph �ڵ�����߼���
  1. ���� user_query��LLM ��������������� PipelineContext��
  2. ���� pipeline.run() ��ȡ PipelineOutput��
  3. �����д�� AgentState�����յ� fallback �����д��ɽṹ����¼ warning��
- PipelineState + PipelineOutput��
  - PipelineState ��ִ�����ۼ������б�����ѡ map��confirmed/ambiguous��֪ʶ payload �ȡ�
  - PipelineOutput �����ṩ���ղ��confirmed_terms��mbiguous_terms��enriched_query��	erm_hints��knowledge_payload��knowledge_snippets��mode=fresh/fallback����

## 4. ������
1. **LLM ������** _extract_concept_terms
   - ���룺user_query + LLM��
   - Prompt Ҫ����� JSON list������ҵ������������ʣ�������ʧ��ֱ�����쳣���� fallback��
2. **��ѡ����** _search_candidates_for_terms
   - ���룺�����б���
   - ���ε��� search_all_candidates(term)���ۺ�Ϊ dict[mention, list[Candidate]]��
3. **���崦��** _disambiguate_candidates
   - ���룺��ѡ map + ԭʼ���⡣
   - ���� datacloud_knowledge.intent.matching.disambiguate_candidates���õ� confirmed_terms + ambiguous_terms��
4. **֪ʶ����** _load_knowledge_for_confirmed
   - ���룺confirmed_terms��
   - ͨ�� knowledge_service.load_term_knowledge(term_id) ��ȡ���鲢�ϲ�Ϊ���� knowledge_payload������ָ��/ά��/�����ȣ���
5. **��������** _build_outputs
   - ���� confirmed ������� enriched_query���������׼���滻/ע�ͽ��û����⣩��	erm_hints�����ݾɸ�ʽ����knowledge_snippets���� payload ѡƬ�Σ���

## 5. AgentState д��
- ����ģʽ��
  - concept_terms: list[str]
  - confirmed_terms: list[ConfirmedTermDict]
  - mbiguous_terms: list[AmbiguousTermDict]
  - enriched_query: str
  - knowledge_payload: dict[str, Any]
  - 	erm_hints: list[dict[str, Any]]�����ݾɸ�ʽ��
  - knowledge_snippets: list[str]
  - ɾ�� knowledge_preview������д�룩��
- fallback ģʽ��ֻд 	erm_hints/enriched_query/knowledge_snippets�������ÿղ���¼ state.knowledge_mode="fallback"��������ѡ�ֶΣ��������Ų飩��

## 6. Fallback ����
- ��һ���׳��쳣 �� ����ִ�� _fallback_search_knowledge��
  - ���� search_knowledge.ainvoke({"query": user_query})��
  5- ����Ӧ����ȡ���ֶΣ�	erm_matches �� term_hints��knowledge_snippets �ȣ���
  - PipelineOutput.mode = "fallback"����־��ӡ�쳣ԭ�� + fallback ���� ID��
- fallback ���ٵݹ���� pipeline�������ظ�����

## 7. ��־
- logger.info��������ֹ��ģʽ��fresh/fallback����
- logger.debug��
  - �����ȡ��concept_term_count��ԭ����Ƭ�Ρ�
  - ��ѡ������ÿ�� mention �ĺ�ѡ������
  - ���壺confirmed �� ambiguous ������
  - ֪ʶ���أ��ɹ�/ʧ�ܵ� 	erm_id �б���
  - �������ɣ�	erm_hints ������knowledge_snippets ������
- logger.warning��fallback ԭ��logger.exception ���ڵ���ģʽ�����á�

## 8. ����
- 	ests/dca/unit/test_knowledge_enhance_pipeline.py
  - **test_pipeline_happy_path**��LLM stub �������������֤ confirmed/ambiguous д�롣
  - **test_pipeline_disambiguate_returns_empty**����ѡ���ڵ�ȫ�� ambiguous��
  - **test_pipeline_fallback_on_llm_error**��LLM ���쳣 �� fallback ����ɽṹ��
- ������ 	est_knowledge_enhance_node.py�����¶��� AgentState �ֶΣ�����ɾ�� knowledge_preview��
- Mocks��
  - LLM wrapper���̶� JSON����
  - search_all_candidates��disambiguate_candidates��knowledge_service.load_term_knowledge��

## 9. ���� & TODO
- knowledge_service ���ܲ�����ͳһ��ڣ���Ҫ���� datacloud-knowledge ��������������
- AgentState schema ���ڱ𴦶��壨pydantic/dataclass������Ҫͬ����������ע�⡣
- �����ɰ� pipeline ��������Ϊ�����࣬�������ڵ㣨����ͼ���壩���á�
