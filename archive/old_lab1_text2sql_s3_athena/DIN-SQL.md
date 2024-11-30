# DIN-SQL (Decomposed In-Context Learning of Text-to-SQL with Self-Correction)

Paper - https://arxiv.org/pdf/2304.11015.pdf

## 배경 - Few shot 에러 유형 분석
- Schema Linking 오류
    - Schema Linking - 자연어 질문을 바탕으로, 스키마에서 활용할 테이블/컬럼을 선택하고, 원하는 쿼리를 작성
    - 테이블 / 컬럼 / 엔티티를 잘못 가져와서 에러 발생 - Wrong Table / Column
- JOIN 처리 오류 
    - 테이블 / Foreign Key 등을 잘못 가져옴
- GROUP BY 처리 오류
    - GROUP BY 처리를 누락하거나, 잘못된 컬럼을 활용
    - nested 작업에서의 오류 / SQL 문법 오류 등

<img src="./images/error-types.png" width="400">


## DIN-SQL 모듈 구성의 Motivation
- Schema Linking 모듈 - Wrong table, column 문제 해결
- Classification & Decomposition 모듈 - Grouping, Nesting, Joins, Set 작업 등의 문제 해결
- SQL Generation 모듈 - Grouping, Nesting, Joins, Set 작업 등의 문제 해결
- Self-Correction - SQL 문법 오류 해결

<img src="./images/din-sql.png" width="700">


## Schema Linking 모듈 (few-shot)
- 데이터베이스 내에서 자연어 질의와 연관된 테이블 및 컬럼 식별
- 입력: {Table 정보} + {Q. 유저 질문} + {A. 스키마 링크를 찾기 위한 Chain of Thought 유도 인스트럭션 (`Let's think step by step`)}
- 출력: LLM에서 스키마 링크 생성

<img src="./images/schema-linking.png" width="500">


## Classification & Decomposition 모듈 (few-shot)
<img src="./images/classification-decomposition.png" width="500">

### Classification
- 쿼리 종류를 나눠서, 어려움의 정도에 따라, LABEL을 지정해서 접근방법을 바꿈
    - `EASY`: 하나의 테이블에서 해결 가능한 쿼리로 예상
    - `NON-NESTED`: 서브쿼리는 없지만, 여러 테이블의 JOIN 같은 복잡한 구문이 포함된 쿼리로 예상
    - `NESTED`: 서브쿼리가 존재하며, JOIN 및 UNION 연산자 포함된 쿼리로 예상
- Non-Nested & Nested 쿼리에 Chain of Thought 유도 인스트럭션 적용 (`Let's think step by step`)

### Decomposition
- Nested로 분류되는 질문은 하위 질문을 생성해서, 작은 문제로 분해(decomposition)해서 처리하도록 유도

## SQL Generation 모듈 (few-shot)
- EASY로 분류된 task는 질문 + 스키마링크를 제공해서 바로 쿼리 생성
- Non-nested 단계부터 스키마링크와 함께 CoT 유도 및 intermediate representation 생성 인스트럭션 생성
    - 모델은 Intermediate_representation을 만들고, 이걸 활용해 최종 SQL 구문 생성
- Nested 쿼리에는 Decomposition 모듈의 처리 결과에 따라 sub-question이 존재
    - sub-question에 대한 SQL 쿼리를 먼저 만들고, 이에 대한 intermediate representation을 만든 이후에 SQL 생성
    - sub SQL을 Nested 구조로 최종 답변 생성

## Self Correction 모듈 (zero-shot)
- 놓치거나 중복되는 코드를 수정
- Generic Self-correction 프롬프트 활용
    - `Fix bugs in the below SQL for the given question`
- Gentle Self-correction 프롬프트 활용
    - `For the given question, use the provided tables, columns, foreign keys, and primary keys to fix the given ... If there are any problems, fix them.`
- Self Correction만 zero-shot으로 처리하고, 나머지 모듈들은 10개의 CoT 샘플을 few shot으로 제공


#### Citation
```
@article{pourreza2023din,
  title={DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction},
  author={Pourreza, Mohammadreza and Rafiei, Davood},
  journal={arXiv preprint arXiv:2304.11015},
  year={2023}
}
Paper: https://arxiv.org/abs/2304.11015
Code: https://github.com/MohammadrezaPourreza/Few-shot-NL2SQL-with-prompting
```