export const analysisLabels:Record<string,string>={
 awaiting_ai:'AI шинжилгээний дараалалд',pending:'Боловсруулалт хүлээж байна',ai_complete:'AI шинжилгээ бэлэн',ai_unavailable:'AI түр боломжгүй · дахин оролдоно',metadata_only:'Зөвхөн гарчиг, эх сурвалжийн мэдээлэл',lexical_only:'Үгийн түвшний шинжилгээ',complete:'Боловсруулалт дууссан',fallback:'AI бүрэн дуусаагүй · хязгаарлагдмал үр дүн',unverified:'Эх сурвалжаар нягтлаагүй',person:'Хүн',organization:'Байгууллага',location:'Байршил',event:'Үйл явдал'};
export const analysisLabel=(value:string)=>analysisLabels[value]||value;
