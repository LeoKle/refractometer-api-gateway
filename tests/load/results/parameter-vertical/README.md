Load Test with 2x CPU and RAM:
Replica: 1
CPU-Limit: 2
Memory-Limit: 2Gi

4750_v1: FAIL: dial i/o timeout errors

NAME                                CPU(cores)   MEMORY(bytes)   
api-gateway-68dcf9bdf7-vvnlh        2m           77Mi
mongo-parameter-0                   260m         199Mi
parameter-service-8b466f8c8-srj77   1036m        258Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   1453m        9%       3712Mi          11%

---

add 

```
- --timeout-keep-alive
- "30"
```

4750_v2: PASS
9500: FAIL http_req_duration
7125: PASS
8312: PASS
8906: PASS
9203: FAIL: http_req_duration crossed

NAME                                CPU(cores)   MEMORY(bytes)
api-gateway-68dcf9bdf7-vvnlh        1m           77Mi 
mongo-parameter-0                   752m         300Mi
parameter-service-68c894ccf-x7wgw   2002m        387Mi

NAME       CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
server-l   2901m        18%      3922Mi          12%


deployment.yaml:
```
apiVersion: v1
kind: Service
metadata:
  name: parameter-service
  labels:
    app: parameter-service
spec:
  type: NodePort
  selector:
    app: parameter-service
  ports:
    - port: 80
      targetPort: 8000
      nodePort: 30081
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: parameter-service
  labels:
    app: parameter-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: parameter-service
  template:
    metadata:
      labels:
        app: parameter-service
    spec:
      containers:
        - name: parameter-service
          image: ghcr.io/leokle/refractometer-backend-parameter-service:latest
          imagePullPolicy: Always
          command: ["uvicorn"]
          args:
            - api.app:app
            - --host
            - "0.0.0.0"
            - --port
            - "8000"
            - --app-dir
            - src
            - --loop
            - "uvloop"
            - --http
            - "httptools"
            - --no-access-log
            - --log-level
            - "warning"
            - --backlog
            - "4096"
            - --timeout-keep-alive
            - "30"
          ports:
            - containerPort: 8000
          env:
            - name: MONGO_URI
              value: mongodb://mongo-parameter:27017
            - name: WEB_CONCURRENCY
              value: "4"
          resources:
            requests: { cpu: "2", memory: 2Gi }
            limits: { cpu: "2", memory: 2Gi }

```