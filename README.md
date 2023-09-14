# Onfido Service

A service to handle Onfido KYC.

Requires the following permissions in Rehive:

permissions |
---|
admin.company.view |
admin.webhook.add |
admin.document.view |
admin.document.change |
admin.user.view |
admin.user.change |


## Getting started

To run the codebase locally you need several things:

1. Git - self explanatory
1. Python - We suggest using Anaconda as it has some handy tools like virtual environment management.
2. Docker - We use docker for redis and postgres locally.
4. Docker Compose - Install this as well if your docker distribution doesn't come with it by default.

First, clone the rehive-core repository.

```bash
git clone git@github.com:rehive/service-onfido.git
```

Once this is done you will need to add a `.env` file in the project root. Request this from another Rehive team member.

Second, set up a virtual environment using conda (or whatever venv alternative you prefer):

```bash
conda create -n {env_name} python=3.10
```

Next, activate the environment within the rehive-core project root:

```bash
source activate {env_name}
```

Next, spin up the required docker containers:

```bash
docker-compose up -d postgres
```

You could spin up all the containers and run the code in "production" mode but this is generally not worth the effort as you don't get the benefit of hot code reloading offered by running the Django part of the application separately.

Install requirements
```bash
pip install -r requirements.txt
```

You should now run migrations (from within the project root):

```bash
./src/manage.py migrate
```

Finally, you can run the django server:

```bash
./src/manage.py runserver
```

If you go to http://localhost/8000/swagger you will see the web interface for the platform.
