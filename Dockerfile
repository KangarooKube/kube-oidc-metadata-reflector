FROM python:3.12-alpine

ARG USER_NAME=containeruser
ARG USER_UID=1000
ARG USER_GID=$USER_UID
ARG GROUP_NAME=$USER_NAME

COPY app /app

WORKDIR /app

# RUN apt update \
#     && apt upgrade -y \
#     && pip3 install --no-cache-dir -r requirements.txt \
#     && groupadd --gid $USER_GID $USERNAME \
#     && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME 

RUN pip3 install --no-cache-dir -r requirements.txt \
    && addgroup --gid $USER_GID $GROUP_NAME \
    && adduser -D -h $(pwd) -G $GROUP_NAME -H -u $USER_UID $USER_NAME
# --ingroup $USERNAME
USER $USER_NAME

EXPOSE 8080

ENTRYPOINT [ "python3", "/app/main.py" ]