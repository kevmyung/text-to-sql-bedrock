# 실습 사전 구성 가이드

이 문서는 실습 환경을 준비하는 과정을 단계별로 설명합니다.

## Step 1. 실습 계정 접속

1. **이메일 OTP 인증 선택**

   ![OTP 인증](./images/Event_Engine_OTP.png)

2. **이메일로 전송된 Passcode 입력**

   ![Passcode 입력](./images/Event_Engine_New_Email.png)

3. **AWS 콘솔 열기**

   좌측 하단의 **Open AWS console** 버튼을 클릭하여 실습 계정으로 이동합니다.

   ![AWS 콘솔 로그인](./images/Event_Engine_Detail.png)

## Step 2. 실습 자원 배포

1. `cloudformation/cf-txt2sql.yaml` 파일을 [다운로드](https://github.com/kevmyung/text-to-sql-bedrock/blob/main/cloudformation/cf-txt2sql.yaml)합니다.

2. [CloudFormation 콘솔](https://us-west-2.console.aws.amazon.com/cloudformation/home?region=us-west-2#/stacks/create)로 이동합니다.

3. **Oregon (us-west-2) 리전**에서 실습 진행 여부를 확인합니다.

4. **Upload a template file**을 선택 후, 다운로드 받은 `cf-txt2sql.yaml` 파일을 업로드하고, **Next** 버튼을 클릭합니다.
   
   ![CloudFormation Template Upload](./images/CloudFormation-1.png)

5. Stack name으로 `gen-ai-workshop`을 입력하고, **Next** 버튼을 클릭합니다.

6. 하단의 **I acknowledge that AWS CloudFormation might create IAM resources** 체크 박스를 선택한 후, **Submit** 버튼을 누릅니다.

7. 자원 생성 완료까지 약 30분 소요됩니다.

## [Optional] 파일 업로드가 안되는 경우
1. Console 하단 CloudShell 오픈
2. 아래 명령어 실행
```shell
git clone https://github.com/kevmyung/text-to-sql-bedrock.git
aws cloudformation create-stack --stack-name gen-ai-workshop --template-body file://text-to-sql-bedrock/cloudformation/cf-txt2sql.yaml --capabilities CAPABILITY_NAMED_IAM
```


## Step 3. Bedrock 초기 설정

1. [Bedrock 콘솔](https://us-west-2.console.aws.amazon.com/bedrock/home?region=us-west-2#/)로 이동합니다.

2. 좌측 탭 하단의 **Model access** 버튼을 클릭하거나, 이 [링크](https://us-west-2.console.aws.amazon.com/bedrock/home?region=us-west-2#/modelaccess)를 통해 이동합니다.

3. Amazon & Anthropic 모델 전체를 선택하고, 하단의 **Save changes** 버튼을 누릅니다.
   
   ![모델 액세스 설정](./images/Model-Access.png)

4. 잠시 후 모델의 Access status가 `Access granted`로 변경됩니다.

실습 준비가 완료되었습니다. 진행자의 안내에 따라 실습을 진행해 주세요.
