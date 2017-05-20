#!/usr/bin/node

var fs = require("fs");
var path = require("path");
var pty = require("pty.js");
var WebSocketServer = require('ws').Server;
var express = require("express");
var app = express();
var http = require("http");
var https = require("https");
var querystring = require("querystring");

var Inotify = require("inotify").Inotify;
var inotify = new Inotify();

var raven = require("raven");
if (fs.existsSync("raven.dsn")) {
    raven.config(fs.readFileSync("raven.dsn", "utf8")).install();
}

var uuid = require("uuid/v4");

var terminals = {};

app.set("port", (process.env.PORT || 8301));

var server = require("http").createServer(app);
server.listen(app.get("port"));

app.post("/ws/terminal/:id/size", function(req, res) {
    res.setHeader("Content-Type", "application/json");
    var id = req.params.id;
    if (typeof terminals[id] !== "undefined") {
        var rows = parseInt(req.query.rows);
        var cols = parseInt(req.query.cols);
        terminals[id].resize(cols, rows);
        res.send(JSON.stringify({ success: true }));
    }
    else {
        res.send(JSON.stringify({ success: false }));
    }
    res.end();
});

var onlineUsers = {};
var wss = new WebSocketServer({ server: server });
wss.on("connection", function(ws) {
    var id = uuid();
    var started = false;
    var term = null;
    ws.on("close", function() {
        if (term) {
            term.destroy();
        }
        delete terminals[id];
    });
    var message_init = function(data, flags) {
        data = JSON.parse(data);
        var postData = querystring.stringify({
            uid: data.uid,
            sid: data.site,
            vmid: data.vm,
            access_token: data.token
        });
        var req = http.request({
            method: "POST",
            hostname: "localhost",
            port: 601,
            path: "/wsauth",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": postData.length
            }
        }, function(resp) {
            resp.setEncoding("utf8");
            resp.on("data", function(authinfo) {
                try {
                    var auth = JSON.parse(authinfo);
                }
                catch (err) {
                    raven.captureException(err);
                    ws.send(JSON.stringify({ error: "Failed to parse auth server response!" }));
                    ws.close();
                    return;
                }
                if (!auth.granted) {
                    if (auth.exception) {
                        raven.captureMessage(auth.exception);
                    }
                    ws.send(JSON.stringify({ error: auth.error }));
                    ws.close();
                }
                else {
                    if (data.editor) {
                        ws.user = auth.user;
                        function sendUserCount() {
                            var msg = JSON.stringify({
                                action: "users",
                                users: onlineUsers[auth.site_name].sockets.map(function(x) { return x.user; })
                            });
                            for (var i = 0; i < onlineUsers[auth.site_name].sockets.length; i++) {
                                var s = onlineUsers[auth.site_name].sockets[i];
                                if (s.readyState == 1) {
                                    // websocket is in OPEN state
                                    s.send(msg);
                                }
                            }
                        }
                        function addHook(p) {
                            if (!path.join(auth.site_homedir, p).startsWith(auth.site_homedir)) {
                                return;
                            }
                            if (!onlineUsers[auth.site_name] || p in onlineUsers[auth.site_name].hooks) {
                                return;
                            }
                            onlineUsers[auth.site_name].hooks[p] = inotify.addWatch({
                                path: path.join(auth.site_homedir, p),
                                watch_for: Inotify.IN_CREATE | Inotify.IN_DELETE | Inotify.IN_MOVED_FROM | Inotify.IN_MOVED_TO | Inotify.IN_IGNORED | Inotify.IN_DELETE_SELF | Inotify.IN_MODIFY,
                                callback: function(e) {
                                    var act = null;
                                    var stat = null;
                                    if (e.mask & (Inotify.IN_DELETE_SELF | Inotify.IN_IGNORED)) {
                                        delete onlineUsers[auth.site_name].hooks[p];
                                        return;
                                    }
                                    if (e.mask & (Inotify.IN_DELETE | Inotify.IN_MOVED_FROM)) {
                                        act = "delete";
                                    }
                                    if (e.mask & Inotify.IN_MODIFY) {
                                        act = "modify";
                                    }
                                    if (e.mask & (Inotify.IN_CREATE | Inotify.IN_MOVED_TO)) {
                                        act = "create";
                                    }
                                    if (act == "create" || act == "modify") {
                                        try {
                                            stat = fs.lstatSync(path.join(auth.site_homedir, p, e.name));
                                        }
                                        catch (err) {
                                            if (err && err.code == "ENOENT") {
                                                return;
                                            }
                                            else {
                                                raven.captureException(err);
                                            }
                                        }
                                    }
                                    if (act) {
                                        var msg = JSON.stringify({
                                            path: (p ? p : undefined),
                                            type: !!(e.mask & Inotify.IN_ISDIR),
                                            name: e.name,
                                            action: act,
                                            exec: (stat ? ((stat["mode"] & 1) && !stat.isDirectory()) : undefined),
                                            link: (stat ? stat.isSymbolicLink() : undefined)
                                        });
                                        for (var i = 0; i < onlineUsers[auth.site_name].sockets.length; i++) {
                                            var s = onlineUsers[auth.site_name].sockets[i];
                                            if (s.readyState == 1) {
                                                // websocket is in OPEN state
                                                s.send(msg);
                                            }
                                        }
                                    }
                                }
                            });
                        }
                        if (auth.site_name in onlineUsers) {
                            onlineUsers[auth.site_name].sockets.push(ws);
                        }
                        else {
                            onlineUsers[auth.site_name] = {sockets: [ws], hooks: {}};
                        }
                        addHook("");
                        addHook("public");
                        ws.on("close", function() {
                            onlineUsers[auth.site_name].sockets.splice(onlineUsers[auth.site_name].sockets.indexOf(ws), 1);
                            if (!onlineUsers[auth.site_name].sockets) {
                                for (var hook in onlineUsers[auth.site_name].hooks) {
                                    try {
                                        inotify.removeWatch(hooks[hook]);
                                    }
                                    catch (e) {
                                        // watch was already removed
                                    }
                                }
                                delete onlineUsers[auth.site_name];
                            }
                            else {
                                sendUserCount();
                            }
                        });
                        sendUserCount();
                        ws.removeListener("message", message_init);
                        ws.on("message", function(d) {
                            var data = JSON.parse(d);
                            if (data.action == "listen") {
                                addHook(data.path);
                            }
                        });
                    }
                    else {
                        if (data.site) {
                            if (!auth.user) {
                                ws.send(JSON.stringify({ error: "Invalid user id passed!" }));
                                ws.close();
                            }
                            else {
                                term = pty.spawn(__dirname + "/shell.sh", [auth.user], {
                                    name: "xterm-color",
                                    cols: 80,
                                    rows: 30,
                                    cwd: auth.site_homedir,
                                    env: {
                                        SITE_ROOT: auth.site_homedir,
                                        SITE_NAME: auth.site_name,
                                        SITE_PURPOSE: auth.site_purpose
                                    }
                                });
                            }
                        }
                        else if (data.vm) {
                            term = pty.spawn(__dirname + "/ssh.sh", [auth.ip], {
                                name: "xterm-color",
                                cols: 80,
                                rows: 30,
                                env: {
                                    SSHPASS: auth.password
                                }
                            });
                        }
                        term.on("close", function(e) {
                            ws.close();
                            delete terminals[id];
                        });
                        term.on("data", function(data) {
                            ws.send(data);
                        });
                        ws.removeListener("message", message_init);
                        ws.on("message", function(data) {
                            term.write(data);
                        });
                        terminals[id] = term;
                        started = true;
                        if (ws.readyState == 1) {
                            ws.send(JSON.stringify({ id: id, action: "START" }));
                        }
                    }
                }
            });
        });
        req.write(postData);
        req.end();
    };
    ws.on("message", message_init);
});

