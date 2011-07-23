/*
 * Copyright 2007, Martín Ferrari <martin.ferrari@gmail.com>
 * Copyright 2007, Damyan Ivanov <dmn@debian.org>
 *
 * Released under the terms of the GNU GPL 2
 */
function toggle_visibility(id)
{
    var el = document.getElementById(id);
    el.style.display = (el.style.display == 'none' ? 'table-row-group' : 'none');
}
function toggle_visibility2(id)
{
    var el = document.getElementById(id);
    el.style.display = (el.style.display == 'inline' ? 'none' : 'inline');
}
function async_get(id, url)
{
    var xml;
    if (window.XMLHttpRequest) {
	xml = new XMLHttpRequest();
    } else if (window.ActiveXObject) {
	xml = new ActiveXObject("Microsoft.XMLHTTP");
    } else {
	alert("Your browser lacks the needed ability to use Ajax. Sorry.");
	return false;
    }
    xml.open('GET', url);
    xml.onreadystatechange = function() {
	ajaxStateChanged(xml, id);
    };
    xml.send('');
}
function ajaxStateChanged(xml, id)
{
    var el = document.getElementById(id);
    if( !el )
    {
	alert('Element "' + id + '" not found');
	return false;
    }
    if( xml.readyState <= 1 )
    {
	el.innerHTML = el.innerHTML + "<br/>Loading...";
    }
    if( xml.readyState == 3 )
    {
	el.innerHTML = el.innerHTML + ".";
    }
    if( xml.readyState == 4 )
    {
	if( xml.status == 200 )
	{
	    el.innerHTML = xml.responseText;
	}
	else
	{
	    el.innerHTML = xml.status+': '+xml.StatusText;
	}
    }
}
