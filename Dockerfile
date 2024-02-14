FROM ethereum/client-go:stable
RUN apk update && apk add python3 py3-numpy bash gcompat
WORKDIR /home
ENTRYPOINT ["python3"]
