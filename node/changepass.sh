#!/bin/bash

FILE=/srv/emercoind/emercoin.conf
echo -n -e "Установите пароль для соединения RPC JSON к кошельку \nили нажмите [ENTER] (оставит текущий) ":
read -s -t 15 new_pass
echo
old_pass=$(cat $FILE | grep "rpcpassword" | cut -d'=' -f2)

if [ "$new_pass" == "" ]; then
  exit 1
fi
if [ "$new_pass" == "$old_pass" ]; then
  echo "Введенный пароль совпадает с текущим"
  exit 0
 else
   echo -e "\e[31mПароль изменен!\e[0m"
   path=rpcpassword=$new_pass
   sed -i "s#.*rpcpassword.*#$path#g" $FILE
   ./emercoin-cli restart
   exit 0
fi

