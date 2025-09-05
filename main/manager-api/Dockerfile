# Multi-stage Dockerfile for manager-api
# Build with Maven on Eclipse Temurin JDK21 to match source 'release=21'
FROM maven:3.9.6-eclipse-temurin-21 AS build

WORKDIR /app

# Copy source and build
COPY . /app

# Debug JDK version
RUN java -version || true

RUN mvn -B -DskipTests -Dmaven.test.skip=true clean package

# Runtime image (JRE 21)
FROM eclipse-temurin:21-jre

WORKDIR /app

# Copy built jar (assumes Spring Boot fat jar produced in target/)
COPY --from=build /app/target/*.jar /app/app.jar

# Copy optional environment file if present in the repo (do NOT commit secrets to public repo)
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh || true

EXPOSE 8002

ENV JAVA_OPTS=""

ENTRYPOINT ["/app/entrypoint.sh"]


