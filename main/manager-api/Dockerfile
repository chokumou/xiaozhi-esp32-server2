# Multi-stage Dockerfile for manager-api
# Build with Maven on Eclipse Temurin JDK21 to match source 'release=21'
FROM maven:3.9.6-eclipse-temurin-21 AS build

WORKDIR /app

# Copy source and build
COPY . /app

# Debug JDK version
RUN java -version || true

RUN mvn -B -DskipTests clean package

# Runtime image (JRE 21)
FROM eclipse-temurin:21-jre

WORKDIR /app

# Copy built jar (assumes Spring Boot fat jar produced in target/)
COPY --from=build /app/target/*.jar /app/app.jar

EXPOSE 8002

ENV JAVA_OPTS=""

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar /app/app.jar"]


