<?php
// Internal delivery debug protocol from the pinned 1.5.5 binary.
// Packet 873: uint32 sender, int32 command, compact-length octets.
function compact_uint($n) {
    if ($n < 0x80) return pack('C', $n);
    if ($n < 0x4000) return pack('n', $n | 0x8000);
    if ($n < 0x20000000) return pack('N', $n | 0xc0000000);
    return pack('CN', 0xe0, $n);
}
if (count($argv) !== 3 || !in_array($argv[1], array('probe', 'owner', 'battle', 'bidtime'), true)) {
    fwrite(STDERR, "Acao invalida\n"); exit(1);
}
$mode = $argv[1];
$text = $argv[2];
if ($mode === 'bidtime' && !in_array($text, array('0', '327601', '416521'), true)) {
    fwrite(STDERR, "Horario invalido\n"); exit(1);
}
if (in_array($mode, array('owner', 'battle'), true) && !preg_match('/^[1-9][0-9]*-[0-9][0-9]*$/D', $text)) {
    fwrite(STDERR, "IDs invalidos\n"); exit(1);
}
$command = $mode === 'bidtime' ? 1 : ($mode === 'owner' ? 5 : ($mode === 'battle' ? 4 : 999));
$payload = pack('NN', 0, $command) . compact_uint(strlen($text)) . $text;
$packet = compact_uint(873) . compact_uint(strlen($payload)) . $payload;
$socket = stream_socket_client('tcp://172.30.1.8:29300', $errno, $error, 5);
if (!$socket) { fwrite(STDERR, $error . "\n"); exit(1); }
stream_set_timeout($socket, 2);
$offset = 0;
while ($offset < strlen($packet)) {
    $written = fwrite($socket, substr($packet, $offset));
    if (!$written) { fwrite(STDERR, "Falha ao enviar\n"); exit(1); }
    $offset += $written;
}
// This protocol has no direct reply; the host verifies delivery/gs logs.
usleep(300000);
fclose($socket);
echo json_encode(array('sent' => true, 'command' => $command)) . "\n";
