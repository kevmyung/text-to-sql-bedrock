# Pre-Lab Setup Guide

This document explains the step-by-step process to prepare your lab environment.

## Step 1. Accessing the Lab Account

1. **Choose Email OTP Authentication**

   ![OTP Authentication](./images/Event_Engine_OTP.png)

2. **Enter the Passcode sent to your email**

   ![Enter Passcode](./images/Event_Engine_New_Email.png)

3. **Open AWS Console**

   Click on the **Open AWS console** button at the bottom left to move to the lab account.

   ![AWS Console Login](./images/Event_Engine_Detail.png)

## Step 2. Deploy Lab Resources

1. Open CloudShell at the bottom of the Console

2. Run the following commands
```shell
git clone https://github.com/kevmyung/text-to-sql-bedrock.git
aws cloudformation create-stack --stack-name gen-ai-workshop --template-body file://text-to-sql-bedrock/cloudformation/cf-txt2sql.yaml --capabilities CAPABILITY_NAMED_IAM
```

## Step 3. Initial Bedrock Setup

1. Go to the [Bedrock console](https://us-west-2.console.aws.amazon.com/bedrock/home?region=us-west-2#/).

2. Click on the **Model access** button at the bottom of the left tab, or use this [link](https://us-west-2.console.aws.amazon.com/bedrock/home?region=us-west-2#/modelaccess) to navigate.

3. Select all Amazon & Anthropic models, and click the **Save changes** button at the bottom.

   ![Model Access Settings](./images/Model-Access.png)

4. After a moment, the Access status of the models will change to `Access granted`.

The lab preparation is complete. Please proceed with the lab following the instructor's guidance.