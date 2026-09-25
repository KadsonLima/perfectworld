<title> Registration | Perfect World</title>
<head>
<meta http-equiv="content-type" content="text/html"; charset="UTF-8" />
<link rel="stylesheet" type="text/css" href="style.css">
</head>
<body>
<center>
<form id="register" action="?do=register" method=post>
	<br><h3> Registration on the server </h3><br>
	<br><h3> Рerfect World Server 1.5.5 </h3><br>
<center>
Login:<br>
<input class="input_box" type=text name=login><br>
Password:<br>
<input class="input_box" type=password name=passwd><br>
Repeat password:<br>
<input class="input_box" type=password name=repasswd><br>
E-Mail:<br>
<input class="input_box" type=text name=email><br>
<input class="input_submit" type=submit name=submit value="Registration"><br>
</table>
</form>

<?php
$config = array
(
		'host'	=>	getenv('MYSQL_ADDRESS'),
		'user'	=>	getenv('MYSQL_USER'),
		'pass'	=>	getenv('MYSQL_PASSWORD'),
		'name'	=>	getenv('MYSQL_DB'),
		'gold'	=>	getenv('USER_GOLD'),
);

$Zone_ID=1;	//Server zoneid
$A_ID=1;	//Server aid

    if (isset($_POST['login']))
        {
			$link = mysql_connect($config['host'], $config['user'], $config['pass']) or die ("No connection to MySQL");
			mysql_select_db($config['name'], $link) or die ("Database ".$DBName." does not exist o_O");
            
            $Login = $_POST['login'];
            $Pass = $_POST['passwd'];
            $Repass = $_POST['repasswd'];
            $Email = $_POST['email'];
            
            $Login = StrToLower(Trim($Login));
            $Pass = StrToLower(Trim($Pass));
            $Repass = StrToLower(Trim($Repass));
            $Email = Trim($Email);

        if (empty($Login) || empty($Pass) || empty($Repass) || empty($Email))
            {
                echo "All fields are not filled in correctly!";
            }
            
        elseif (ereg("[^0-9a-zA-Z_-]", $Login, $Txt))
            {
                echo "Invalid login format";
            }
            
        elseif (ereg("[^0-9a-zA-Z_-]", $Pass, $Txt))
            {
                echo "Invalid password format"; 
            }
			
        elseif (ereg("[^0-9a-zA-Z_-]", $Repass, $Txt))
            {
                echo "Invalid retry password format";
            }
            
        elseif (StrPos('\'', $Email))
            {
                echo "Invalid E-Mail Format";
            }
            
        elseif ((StrLen($Login) < 4) or (StrLen($Login) > 10))
            {
                echo "The login must contain at least 4 and not more than 10 characters.";
            }
                    else
            {
                $Result = MySQL_Query("SELECT name FROM users WHERE name='$Login'") or ("Can't execute query.");
                
        if (MySQL_Num_Rows($Result))
            {
                echo "<font color='red'>Login</font> <b>".$Login."</b> <font color='red'>already exists in the database -_-</font>";
            }
            
        elseif ((StrLen($Pass) < 4) or (StrLen($Pass) > 10))
            {
                echo "The password must contain at least 4 and not more than 10 characters.";
            }
            
        elseif ((StrLen($Repass) < 4) or (StrLen($Repass) > 10))
            {
                echo "Repeat password must contain at least 4 and not more than 10 characters.";
            }
            
        elseif ((StrLen($Email) < 4) or (StrLen($Email) > 25))
            {
                echo "E-Mail must contain at least 4 and not more than 25 characters.";
            }
		else
			{
				$Result = MySQL_Query("SELECT name FROM users WHERE name='$Email'") or ("Can't execute query.");
		if (MySQL_Num_Rows($Result))
			{
				echo "<font color='red'>E-Mail</font> <b>".$Email."</b> <font color='red'>already exists in the database -_-</font>";
			}
            
        elseif ($Pass != $Repass)
            {
                echo "Passwords do not match.";
            }        
        else
            {
				$Salt = base64_encode(md5($Login.$Pass, true));
				MySQL_Query("call adduser('$Login', '$Salt', '0', '0', '0', '0', '$Email', '0', '0', '0', '0', '0', '0', '0', '', '', '$Salt')") or die ("Account not registered");
				$mysqlresult=MySQL_Query("select * from `users` WHERE `name`='$Login'");
				$User_ID=MySQL_result($mysqlresult,0,'ID');
				MySQL_Query("call usecash({$User_ID},{$Zone_ID},0,{$A_ID},0,".$config['gold'].",1,@error)") or die ("Gold is not issued");
				echo "<font color='green'>Account name <b>".$Login."</b> successfully registered :) User ID: ".$User_ID." <br/> ".$config['gold']." If Gold was applied it will be available in 5-10 minutes.";
			}
			}
		}
	}
?>
