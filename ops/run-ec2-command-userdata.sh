#!/bin/bash -ex

# Tell SNS all about it
function notify_sns
{{
    if [ {aws_sns_arn} ]; then
        aws --region {aws_region} sns publish --topic-arn {aws_sns_arn} --subject "$1" --message "$1"
    fi
}}

notify_sns 'Starting {command_name}...'

# Bail out with a log message
function shutdown_with_log
{{
    if [ $1 = 0 ]; then
        notify_sns "Completed {command_name} - `uptime --pretty`"
    else
        notify_sns "Failed {command_name} - `uptime --pretty`"
    fi

    mkdir /tmp/task
    gzip -c /var/log/cloud-init-output.log > /tmp/task/cloud-init-output.log.gz
    echo {command} > /tmp/task/command
    echo $1 > /tmp/task/status

    aws s3 cp /tmp/task s3://{bucket}/{log_prefix}/ --recursive --acl private

    shutdown -h now
}}

# Bail out when the timer reaches zero
( sleep {lifespan}; shutdown_with_log 2 ) &

# Prepare temp volume, if applicable
if [ -b /dev/nvme1n1 ]; then
    mkfs.xfs /dev/nvme1n1
    mount /dev/nvme1n1 /tmp
fi

# Install machine
aws s3 cp s3://data.openaddresses.io/config/environment-{major_version}.txt /etc/environment
aws s3 cp s3://data.openaddresses.io/docker/openaddr-machine-{patch_version}.tar.gz /tmp/img.tgz
gunzip -c /tmp/img.tgz | docker load

# Run the actual command
docker run --env-file /etc/environment \
    --volume /tmp:/tmp --net="host" openaddr/machine:{patch_version} \
    {command} && shutdown_with_log 0 || shutdown_with_log 1 2>&1
