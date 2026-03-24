const API = "https://b1-cedy.onrender.com";

let userEmail = "";
let isAdmin = false;

/* PAGE SWITCH */
function showPage(page){
  document.querySelectorAll(".page").forEach(p=>p.style.display="none");
  document.getElementById(page).style.display="block";

  if(page==="dashboard") loadChildren();
}
showPage("login");

/* SIGNUP */
function signup(){
  fetch(API+"/signup",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      name: document.getElementById("su_name").value,
      email: document.getElementById("su_email").value,
      password: document.getElementById("su_pass").value
    })
  })
  .then(r=>r.json())
  .then(d=>{
    alert(d.message || "Signup Done");
    showPage("login");
  });
}

/* LOGIN */
function login(){
  fetch(API+"/login",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      email: document.getElementById("login_email").value,
      password: document.getElementById("login_pass").value
    })
  })
  .then(r=>r.json())
  .then(d=>{
    if(d.status==="admin"){
      isAdmin = true;
      userEmail = "";
      alert("Admin Login");
      showPage("dashboard");
    }
    else if(d.status==="user"){
      isAdmin = false;
      userEmail = d.email;   // 🔥 auto email
      alert("User Login");
      showPage("dashboard");
    }
    else{
      alert("Login Failed");
    }
  });
}

/* LOAD CHILDREN */
function loadChildren(){
  fetch(API+"/get_children")
  .then(r=>r.json())
  .then(data=>{
    let container = document.getElementById("childrenContainer");
    container.innerHTML="";

    data.forEach(c=>{
      let card=document.createElement("div");
      card.className="childCard";

      let delBtn = isAdmin
        ? `<button onclick="deleteChild(${c.id})">Delete</button>`
        : "";

      card.innerHTML = `
        <h4>${c.name}</h4>
        <p>Age: ${c.age}</p>
        <p>${c.place}</p>
        ${delBtn}
      `;

      container.appendChild(card);
    });
  });
}

/* DELETE */
function deleteChild(id){
  if(!confirm("Delete child?")) return;

  fetch(API+"/delete_child/"+id,{method:"DELETE"})
  .then(()=>{
    alert("Deleted");
    loadChildren();
  });
}

/* REGISTER CHILD */
function registerChild(){
  let f=new FormData();
  f.append("name", document.getElementById("child_name").value);
  f.append("age", document.getElementById("child_age").value);
  f.append("place", document.getElementById("child_place").value);
  f.append("photo", document.getElementById("child_photo").files[0]);

  fetch(API+"/register_child",{method:"POST",body:f})
  .then(r=>r.json())
  .then(d=>{
    alert(d.message || "Registered");
    showPage("dashboard");
  });
}

/* IMAGE CHECK */
function crossCheck(){
  let f=new FormData();
  f.append("photo", document.getElementById("check_photo").files[0]);
  f.append("user_email", userEmail);

  fetch(API+"/crosscheck",{method:"POST",body:f})
  .then(r=>r.json())
  .then(d=>{
    showPage("result");

    let resultText = document.getElementById("result_text");
    let details = document.getElementById("family_details");

    if(d.status==="found"){

      alert("MATCH FOUND ✅");

      resultText.innerHTML =
        d.match_type==="age_progression"
        ? "AGE PROGRESSION MATCH FOUND"
        : "MATCH FOUND";

      details.innerHTML =
        `Name: ${d.name}<br>Age: ${d.age}<br>Place: ${d.place}`;
    }

    else if(d.status==="no face"){
      alert("NO FACE DETECTED ❌");
      resultText.innerHTML="NO FACE DETECTED";
      details.innerHTML="";
    }

    else{
      alert("NOT FOUND ❌");
      resultText.innerHTML="NOT FOUND";
      details.innerHTML="";
    }
  });
}

/* VIDEO DETECTION */
function detectVideo(){
  let f=new FormData();
  f.append("video", document.getElementById("video_file").files[0]);

  fetch(API+"/detect_video",{method:"POST",body:f})
  .then(r=>r.json())
  .then(d=>{
    if(d.status==="found"){
      alert("MATCH FOUND IN VIDEO 🎯");
      console.log(d.results);
    } 
    else{
      alert("NO MATCH FOUND ❌");
    }
  });
}
