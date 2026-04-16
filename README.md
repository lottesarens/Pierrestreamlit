# Pierre
Pierre is een medische chatbot die kan helpen bij alle vragen over problemen bij nierstenen. 

## making and activating the virtual environment in bash 
conda create -n pierre python=3.11 -y
conda activate pierre 

## installing the packages 
pip install -r requirements.txt

## requirements.txt
In this file there is a list of all the modules that we need to install in the virtual environment so that we can make the chatbot. 

## Test.ipynb
This is a jupyter notebook file that we use to test if the base code of our chatbot is working. 

## LICENSE and .gitignore
These are files that are connected to the github repository. The license is just a file that tells people how they get to use the code you make. The .gitignore file is chosen to be python and tells git which files to intentionally ignore. 

## .env
This is a file that will never be shared on github. It is like a secret safe where you can store sensitive information like API's. 